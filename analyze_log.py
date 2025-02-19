import os
import re
import sys
import json
import time
import requests
from requests.auth import HTTPBasicAuth

class JenkinsLogFetcher:
    """
    Diese Klasse kümmert sich darum, das Console-Log eines Jenkins-Jobs
    über die REST-Schnittstelle abzurufen.
    """
    def __init__(self, base_url: str, job_name: str, build_number: str, jenkins_user: str, jenkins_api_token: str):
        """
        base_url: Basis-URL deines Jenkins, z.B. 'https://jenkins.meinefirma.com'
        job_name: Name des fehlgeschlagenen Jobs
        build_number: Buildnummer des fehlgeschlagenen Jobs
        jenkins_user, jenkins_api_token: zur Authentifizierung bei Jenkins
        """
        if not base_url or not job_name or not build_number:
            raise ValueError("Jenkins-Parameter unvollständig. Bitte BASE_URL, FAILED_JOB_NAME und FAILED_BUILD_NUMBER setzen.")
        self.base_url = base_url.rstrip('/')  # trailing slash entfernen
        self.job_name = job_name
        self.build_number = build_number
        self.user = jenkins_user
        self.token = jenkins_api_token

    def get_console_log(self) -> str:
        """
        Ruft das Console-Log von Jenkins ab und gibt es als String zurück.
        """
        console_url = f"{self.base_url}/job/{self.job_name}/{self.build_number}/consoleText"

        try:
            response = requests.get(console_url, auth=HTTPBasicAuth(self.user, self.token), timeout=30)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as req_err:
            print(f"Fehler beim Abrufen des Jenkins-Logs: {req_err}", file=sys.stderr)
            return ""


class LogParser:
    """
    Extrahiert und filtert relevante Fehlermeldungen im Build-Log.
    Sendet nur die letzten X Zeilen weiter, um Kosten zu reduzieren.
    """
    def __init__(self, raw_log: str, max_lines: int = 100):
        """
        raw_log: Vollständiges abgerufenes Log
        max_lines: Anzahl an Zeilen, die am Ende berücksichtigt werden
        """
        self.raw_log = raw_log
        self.max_lines = max_lines

    def extract_errors(self) -> str:
        """
        Durchsucht nur die letzten max_lines des Logs nach typischen Fehlerstichwörtern
        und filtert vertrauliche Daten (z. B. Passwords).
        """
        # Nur die letzten X Zeilen nehmen
        all_lines = self.raw_log.splitlines()
        last_lines = all_lines[-self.max_lines:]  # nur die letzten max_lines

        error_lines = []
        error_pattern = re.compile(r"(error|exception|failed|traceback)", re.IGNORECASE)

        for line in last_lines:
            if error_pattern.search(line):
                # Filtern vertraulicher Daten
                line = re.sub(r"(password|token)\S*", "[REDACTED]", line, flags=re.IGNORECASE)
                error_lines.append(line.strip())

        return "\n".join(error_lines)


class OpenAIClient:
    """
    Kommuniziert mit der OpenAI API:
    - Liest den API-Key aus dem Environment
    - Sendet die Fehlermeldungen zur Analyse
    """
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_TOKEN")
        self.api_url = "https://api.openai.com/v1/chat/completions"
        if not self.api_key:
            raise ValueError("Umgebungsvariable OPENAI_API_TOKEN ist nicht gesetzt.")

    def analyze_errors(self, error_text: str) -> str:
        """
        Sendet den Fehlertext an die OpenAI API und gibt die Analyse zurück.
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        prompt_message = (
            "Analysiere den folgenden Build-Log-Auszug. "
            "Identifiziere mögliche Ursachen, Fehlerquellen und mache Vorschläge zur Behebung:\n\n"
            f"{error_text}\n\n"
        )

        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "Du bist ein DevOps-Experte, der Fehlerlogs analysiert."},
                {"role": "user", "content": prompt_message}
            ],
            "temperature": 0.0
        }

        try:
            response = requests.post(self.api_url, headers=headers, data=json.dumps(payload), timeout=30)
            response.raise_for_status()
            response_data = response.json()
            return response_data["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as req_err:
            return f"Fehler bei der Anfrage an die OpenAI API: {req_err}"
        except KeyError:
            return "Unerwartete Antwortstruktur von der OpenAI API erhalten."

    def analyze_errors_with_retry(self, error_text: str, retries=1, delay=20) -> str:
        """
        Führt analyze_errors mit mehreren Versuchen aus, falls ein 'Too Many Requests' (429) Fehler auftritt.
        Reduzierte Retry-Zahl und längere Wartezeit, um unnötige Kosten zu vermeiden.
        """
        for attempt in range(retries):
            result = self.analyze_errors(error_text)
            if "Too Many Requests" not in result and "429" not in result:
                return result
            print(f"Rate Limit überschritten. Warte {delay} Sekunden... (Versuch {attempt+1}/{retries})", file=sys.stderr)
            time.sleep(delay)
        return "Fehlgeschlagen: Rate Limit wurde mehrfach überschritten."


class BuildAnalyzer:
    """
    Koordiniert den Ablauf:
    1. JenkinsLogFetcher ruft das Log des fehlgeschlagenen Jobs ab
    2. LogParser filtert die letzten X Zeilen und extrahiert relevante Fehler
    3. OpenAIClient analysiert das Ganze (mit Retry bei Rate-Limit)
    4. Ausgabe erfolgt im stdout
    """
    def __init__(self, jenkins_base_url: str, job_name: str, build_number: str, jenkins_user: str, jenkins_token: str):
        self.log_fetcher = JenkinsLogFetcher(jenkins_base_url, job_name, build_number, jenkins_user, jenkins_token)
        self.openai_client = OpenAIClient()

    def run_analysis(self):
        raw_log = self.log_fetcher.get_console_log()
        if not raw_log:
            print("Konnte kein Log abrufen. Abbruch.")
            return

        # Beim Erzeugen des LogParsers nur die letzten X Zeilen betrachten
        parser = LogParser(raw_log, max_lines=100)
        error_text = parser.extract_errors()
        if not error_text:
            print("Keine relevanten Fehler im abgerufenen Log gefunden.")
            return

        analysis_result = self.openai_client.analyze_errors_with_retry(error_text)
        print(analysis_result)


def main():
    jenkins_base_url = "https://jenkins-clemens01-0.comquent.academy/"
    failed_job_name = os.getenv("FAILED_JOB_NAME")
    failed_build_number = os.getenv("FAILED_BUILD_NUMBER")

    jenkins_user = "admin"
    jenkins_token = os.getenv("JENKINS_API_TOKEN")

    try:
        analyzer = BuildAnalyzer(
            jenkins_base_url,
            failed_job_name,
            failed_build_number,
            jenkins_user,
            jenkins_token
        )
        analyzer.run_analysis()
    except ValueError as e:
        print(f"Konfigurationsfehler: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Allgemeiner Fehler: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
