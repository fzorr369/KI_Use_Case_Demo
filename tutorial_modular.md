# Predictive Maintenance mit SAP APM - Modulares System

Diese Anleitung erklärt das modulare Predictive Maintenance System für SAP APM. Das System besteht aus zwei Hauptkomponenten: einem proaktiven Monitoring-Server und einem Dataset-Upload-Tool. Beide nutzen eine gemeinsame, zentrale Konfiguration für maximale Übertragbarkeit.

---

## 🏗️ Systemarchitektur

### Hauptkomponenten

1. **`serverHostingCombined_with_APM_tutorial.py`** - Proaktiver Monitoring-Server
   - Lädt ML-Modell aus AWS S3
   - Initialisiert APM-Indikatoren und holt echte Characteristic IDs
   - Polling-Schleife: Holt kontinuierlich neue Sensordaten von APM
   - Führt Vorhersagen aus und erstellt Alerts bei Ausfallrisiko
   - Bietet Flask-API für manuelle Tests

2. **`send_apm_dataset.py`** - Dataset Upload Tool
   - Lädt Trainingsdaten aus CSV-Dateien
   - Initialisiert APM-Indikatoren (gleiche Logik wie Server)
   - Sendet Datenpunkte an APM im 15-Sekunden-Takt
   - Simuliert Echtzeit-Datenstreaming für Tests

### Zentrale Konfiguration

Beide Komponenten nutzen **identische Mapping-Logik** für maximale Konsistenz:

```python
# WICHTIG: Reihenfolge entspricht der vom Modell erwarteten Feature-Reihenfolge!
APM_MERKMAL_TO_MODEL_FEATURE_MAP = {
    "PRODUCT_QUALITY": "Type",
    "FUMP_ROT_SPEED_RPM": "Rotational speed [rpm]",
    "FUMP_TRQ_NM": "Torque [Nm]",
    "FUMP_TOOL_WEAR": "Tool wear [min]",
    "PUMP_AIR_TEMPERATURE": "Air temperature [C]",
    "PUMP_PROCESS_TEMPERATURE": "Process temperature [C]",
    "PUMP_TEMPERATURE_DIFFERENCE": "Temperature difference [C]"
}

# Automatisch generierte Listen in korrekter Reihenfolge
MERKMAL_NAMES = list(APM_MERKMAL_TO_MODEL_FEATURE_MAP.keys())
FEATURE_NAMES = list(APM_MERKMAL_TO_MODEL_FEATURE_MAP.values())
```

---

## 🔧 Anpassung für neue Use Cases

### Schritt 1: Feature-Mapping definieren

**Das Mapping ist der Schlüssel zur Übertragbarkeit!** Es verbindet APM-Merkmalsnamen mit Modell-Features.

#### Wichtige Regeln:

1. **Linke Seite** = Exakter APM-Merkmalname (z.B. `"FUMP_TRQ_NM"`)
2. **Rechte Seite** = Exakter Modell-Feature-Name (z.B. `"Torque [Nm]"`)
3. **Reihenfolge** = Muss der Modell-Trainingsreihenfolge entsprechen!

#### Wo finde ich die Namen?

- **APM-Merkmalsnamen**: SAP APM → Equipment Management → Indikatoren
- **Modell-Feature-Namen**: Aus dem Trainings-DataFrame oder `model.feature_names_in_`

### Schritt 2: Umgebungsvariablen konfigurieren

Erstelle eine `.env`-Datei mit allen erforderlichen Konfigurationen:

```bash
# APM OAuth Konfiguration
APM_OAUTH_TOKEN_URL=https://your-apm-instance/oauth/token
APM_OAUTH_CLIENT_ID=your_client_id
APM_OAUTH_CLIENT_SECRET=your_client_secret
APM_X_API_KEY=your_api_key

# APM Endpunkte
APM_INDICATOR_DATA_ENDPOINT=https://your-apm-instance/IndicatorService/v1/Indicators
APM_TIMESERIES_ENDPOINT=https://your-apm-instance/TimeseriesService/v1/Measurements
APM_ALERT_CREATION_ENDPOINT=https://your-apm-instance/AlertService/v1/Alerts

# Equipment Konfiguration
APM_EQ_NUMBER=10003500
APM_EQ_SSID=S19CLNT100
APM_EQ_TYPE=EQUI
APM_ALERT_TYPE=your_alert_type

# AWS S3 Konfiguration (für Modell)
S3_BUCKET=your-model-bucket
MODEL_KEY=models/your_model.pkl.gz
AWS_REGION=eu-central-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key

# Polling-Intervall
POLLING_INTERVAL_SECONDS=15
```

### Schritt 3: Modell vorbereiten und hochladen

**Wichtig**: Das Modell muss mit den exakten Feature-Namen und in der korrekten Reihenfolge trainiert werden!

```python
import pickle
import gzip
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

# WICHTIG: Verwende die gleiche Reihenfolge wie im APM_MERKMAL_TO_MODEL_FEATURE_MAP!
FEATURE_NAMES = [
    'Type',
    'Rotational speed [rpm]', 
    'Torque [Nm]',
    'Tool wear [min]',
    'Air temperature [C]',
    'Process temperature [C]',
    'Temperature difference [C]'
]

# Training
X = df_train[FEATURE_NAMES]  # Exakte Reihenfolge!
y = df_train["Target"]

model = RandomForestClassifier()
model.fit(X, y)

# Modell komprimiert speichern (wie im Server erwartet)
with gzip.open("model.pkl.gz", "wb") as f:
    pickle.dump(model, f)

# Validierung der Feature-Reihenfolge
print("Modell erwartet Features in dieser Reihenfolge:")
print(model.feature_names_in_)
```

**Upload nach AWS S3:**
```bash
# Komprimiertes Modell hochladen
aws s3 cp model.pkl.gz s3://your-bucket/models/your_model.pkl.gz
```

---

## 🚀 System starten und testen

### 1. Monitoring-Server starten

```bash
# Virtuelle Umgebung aktivieren
source .venv/bin/activate

# Server starten
python serverHostingCombined_with_APM_tutorial.py
```

**Erwartete Ausgabe:**
```
✅ Modell erfolgreich geladen
==========================================================
INFO: Initialisiere Indikator-Definitionen...
✅ 7 Indikatoren erfolgreich zugeordnet.
==========================================================
INFO: Starte proaktive Monitoring-Schleife...
INFO: Daten werden alle 15 Sekunden von APM abgerufen.
```

### 2. Test-Daten an APM senden

```bash
# In einem neuen Terminal
python send_apm_dataset.py
```

**Das passiert:**
1. ✅ Lädt Dataset (10.000 Zeilen)
2. 🔧 Initialisiert APM-Indikatoren (holt echte Characteristic IDs)
3. 📤 Sendet alle 15 Sekunden einen Datenpunkt an APM
4. 📊 Zeigt Upload-Statistiken

### 3. Flask-API testen (optional)

```bash
# Test-Request an die API
curl -X POST http://localhost:5000/v2/predict \
  -H "Content-Type: application/json" \
  -d '{
    "instances": [{
      "Type": 1.0,
      "Rotational speed [rpm]": 1500.0,
      "Torque [Nm]": 40.0,
      "Tool wear [min]": 50.0,
      "Air temperature [C]": 25.0,
      "Process temperature [C]": 35.0,
      "Temperature difference [C]": 10.0
    }]
  }'
```

---

## 🔧 Kernfunktionen im Detail

### Indikator-Initialisierung (`initialisiere_indikatoren`)

**Was passiert:**
1. Holt OAuth2 Token von APM
2. Ruft IndicatorService auf mit Equipment-Filter
3. Mappt APM-Merkmalsnamen auf Modell-Features
4. Speichert echte Characteristic IDs global
5. Extrahiert Position ID für Payload

**Wichtige Ausgabe:**
```python
char_id_to_name_map_global = {
    '988': 'Torque [Nm]',
    '987': 'Rotational speed [rpm]',
    '989': 'Tool wear [min]',
    # ... weitere Mappings
}
```

### Sensordaten-Abruf (`hole_apm_sensor_daten`)

**Workflow:**
1. Baut TimeseriesService-URL mit Zeitfilter
2. Holt neue Messwerte seit letztem Timestamp
3. Mappt Characteristic IDs auf Feature-Namen
4. Erstellt DataFrame in korrekter Spaltenreihenfolge
5. Füllt fehlende Werte mit 0.0

**Kritisch:** DataFrame wird mit `columns=FEATURE_NAMES` erstellt → Korrekte Reihenfolge!

### Vorhersage-Ausführung (`fuehre_vorhersage_aus`)

```python
def fuehre_vorhersage_aus(input_df):
    # Validiert Spaltenreihenfolge gegen Modell
    model_features = model.feature_names_in_
    current_features = input_df.columns.tolist()
    
    if list(model_features) != current_features:
        print("❌ FEHLER: Spaltenreihenfolge stimmt nicht überein!")
        return
    
    # Vorhersage
    prediction = model.predict(input_df)
    is_failure_risk = bool(prediction[0])
    
    if is_failure_risk:
        print("🔴 Ausfallrisiko erkannt!")
        # erstelle_apm_alert()  # Optional
```

---

## 🐛 Troubleshooting

### Häufige Fehler

#### 1. "Spaltenreihenfolge stimmt nicht überein"

**Problem:** Feature-Reihenfolge im Mapping ≠ Modell-Training

**Lösung:**
```python
# Prüfe Modell-Features
print(model.feature_names_in_)

# Passe APM_MERKMAL_TO_MODEL_FEATURE_MAP entsprechend an
```

#### 2. "positionID must not be null"

**Problem:** Position ID wird nicht korrekt extrahiert

**Lösung:** Prüfe, ob `positionDetails` in APM-Indikator-Response vorhanden

#### 3. "No Access Token"

**Problem:** OAuth-Konfiguration fehlerhaft

**Lösung:** Prüfe `.env`-Datei:
```bash
# Test OAuth manually
curl -X POST $APM_OAUTH_TOKEN_URL \
  -d "grant_type=client_credentials" \
  -d "client_id=$APM_OAUTH_CLIENT_ID" \
  -d "client_secret=$APM_OAUTH_CLIENT_SECRET"
```

#### 4. "Keine Indikatoren gefunden"

**Problem:** Equipment-Filter findet keine Matches

**Lösung:** Prüfe Equipment-Konfiguration:
- `APM_EQ_NUMBER`
- `APM_EQ_SSID` 
- `APM_EQ_TYPE`

---

## 📋 Checkliste für neue Use Cases

### Vorbereitung
- [ ] APM-Merkmalsnamen aus Equipment Management notiert
- [ ] Modell-Feature-Namen aus Training-Code extrahiert
- [ ] `.env`-Datei mit allen Parametern erstellt
- [ ] AWS S3 Bucket und Zugangsdaten konfiguriert

### Anpassung
- [ ] `APM_MERKMAL_TO_MODEL_FEATURE_MAP` angepasst
- [ ] Reihenfolge entspricht Modell-Training
- [ ] Modell mit korrekten Features neu trainiert
- [ ] Modell komprimiert nach S3 hochgeladen

### Testing
- [ ] Server startet ohne Fehler
- [ ] Indikator-Initialisierung erfolgreich
- [ ] Test-Dataset wird erfolgreich gesendet
- [ ] Vorhersagen funktionieren (keine Spalten-Fehler)
- [ ] Alerts werden bei Bedarf erstellt

### Deployment
- [ ] Umgebungsvariablen in Produktionsumgebung gesetzt
- [ ] Monitoring und Logging konfiguriert
- [ ] Backup-Strategie für Modell definiert

---

## 🎯 Fazit

Dieses modulare System ermöglicht:

✅ **Einfache Übertragbarkeit** durch zentrale Mapping-Konfiguration
✅ **Robuste Integration** mit echten APM Characteristic IDs
✅ **Konsistente Datenverarbeitung** zwischen Upload und Monitoring
✅ **Automatische Validierung** der Feature-Reihenfolge
✅ **Skalierbare Architektur** für verschiedene Equipment-Typen

Der Schlüssel liegt in der **korrekten Konfiguration des Feature-Mappings** und der **einheitlichen Nutzung** in beiden Komponenten!

**Wichtig:**
- Die Reihenfolge der Spalten in `FEATURE_NAMES` muss exakt mit der Reihenfolge im Mapping übereinstimmen.
- Das Modell muss beim Laden im Server exakt diese Feature-Namen erwarten, sonst schlägt die Vorhersage fehl.

### Schritt 3: Konfiguration und Secrets

Alle Zugangsdaten und Konfigurationsparameter müssen sicher und korrekt bereitgestellt werden, damit der Server mit SAP APM und ggf. AWS kommunizieren kann.

**a) Beispiel für eine `.env`-Datei (lokal):**
```
APM_OAUTH_TOKEN_URL="https://apm.example.com/oauth/token"
APM_OAUTH_CLIENT_ID="deine-client-id"
APM_OAUTH_CLIENT_SECRET="dein-client-secret"
APM_X_API_KEY="dein-apm-api-key"
S3_BUCKET="mein-bucket"
MODEL_KEY="pfad/zum/model.pkl"
AWS_REGION="eu-central-1"
AWS_ACCESS_KEY_ID="dein-access-key"
AWS_SECRET_ACCESS_KEY="dein-secret-key"
POLLING_INTERVAL_SECONDS=60
```

**b) Secrets für AI Core (Base64-Kodierung):**
Jeder Wert aus der `.env`-Datei muss einzeln base64-kodiert werden:
```bash
echo -n "dein-client-secret" | base64
```
Das Ergebnis trägst du als Wert im AI Core Generic Key (Secret) ein.

**c) Referenzierung im YAML:**
Im Deployment-YAML werden die Secrets wie folgt eingebunden:
```yaml
envFrom:
  - secretRef:
      name: apm-monitoring-secrets
```
Alle Schlüssel aus dem Secret stehen dann als Umgebungsvariablen im Container zur Verfügung.

**Wichtig:** Die Namen der Variablen im Secret müssen exakt den im Code verwendeten Namen entsprechen!

### Schritt 4: Optional – API-Endpunkte erweitern

Wenn du zusätzliche Schnittstellen für eigene Zwecke (z.B. Health-Checks, Trigger, Monitoring) brauchst, kannst du das Flask-API im Hauptskript einfach erweitern.

**Beispiel (in `serverHostingCombined_with_APM_tutorial.py`):**

```python
from flask import Flask, jsonify
app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok"), 200

# ... weitere Endpunkte ...

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```

**Hinweis:**
- Alle neuen Endpunkte müssen in der Flask-App registriert werden.
- Die App kann parallel zur Polling-Schleife laufen, falls gewünscht.

---

## 3. Hosting & Deployment auf SAP AI Core

### a) Docker-Image bauen

Erstelle ein Dockerfile, das dein Skript und alle Abhängigkeiten enthält.

**Beispiel `Dockerfile`:**
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "serverHostingCombined_with_APM_tutorial.py"]
```

Image bauen und pushen:
```bash
docker build -t deinuser/model-server:latest .
docker push deinuser/model-server:latest
```

### b) Pipeline/YAML-Definition für AI Core

**Beispielauszug:**
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: model-server
spec:
  containers:
    - name: model-server
      image: "docker.io/deinuser/model-server:latest"
      command: ["python", "-u", "serverHostingCombined_with_APM_tutorial.py"]
      envFrom:
        - secretRef:
            name: apm-monitoring-secrets
      resources:
        requests:
          cpu: "500m"
          memory: "1Gi"
        limits:
          cpu: "1"
          memory: "2Gi"
```

**Hinweis:** Passe Image-Name, Kommando und Ressourcen je nach Bedarf an.

---

## 3. Hosting & Deployment auf SAP AI Core

### a) Docker-Image bauen

*   Erstelle ein Dockerfile, das alle Abhängigkeiten und dein Skript enthält.
*   Baue das Image und pushe es in eine Registry (z.B. DockerHub, SAP Registry).

### b) Pipeline/YAML-Definition

*   Definiert, wie AI Core dein Image startet.
*   Enthält:
    *   Image-Name
    *   Kommando (z.B. `python -u /app/src/main.py`)
    *   Secrets für Umgebungsvariablen (APM, AWS)
    *   Ressourcenlimits

### c) Deployment

1.  Secrets in AI Core anlegen (Base64-kodiert, alle nötigen Keys).
2.  YAML/Pipeline anpassen und deployen.
3.  Server läuft als Managed Service und übernimmt das Monitoring/Alerting.

---

## 4. Modell-Ladevarianten – Vor- und Nachteile

### a) Laden aus AWS S3

*   Modell wird beim Start aus einem S3-Bucket geladen.
*   Zugangsdaten (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) müssen als Secret bereitgestellt werden.
*   Vorteil: Externes Storage, einfach zu automatisieren.
*   Nachteil: Externer Cloud-Zugriff nötig, Security beachten.

### b) Gemountetes Artefakt in AI Core

*   Modell wird als Artefakt im AI Core Workspace abgelegt und beim Start ins Dateisystem gemountet.
*   Das Skript lädt das Modell direkt von diesem Pfad.
*   Vorteil: Keine externen Cloud-Zugriffe, Lifecycle-Management über AI Core.
*   Nachteil: Muss als Artefakt im Workspace gepflegt werden.

---

## 4. Modell-Ladevarianten

### 4.1 Modell aus AWS S3 laden
Das Modell wird beim Start aus einem S3-Bucket geladen. Die Zugangsdaten werden als Secret bereitgestellt.

**Beispiel (Python):**
```python
import boto3
import pickle
import os

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    region_name=os.environ["AWS_REGION"]
)

bucket = os.environ["S3_BUCKET"]
model_key = os.environ["MODEL_KEY"]
local_model_path = "/tmp/model.pkl"
s3.download_file(bucket, model_key, local_model_path)

with open(local_model_path, "rb") as f:
    model = pickle.load(f)
```
**Wichtig:** Der Pfad `/tmp/model.pkl` ist nur ein Beispiel – stelle sicher, dass du Schreibrechte hast.

### 4.2 Modell als gemountetes Artefakt in AI Core
Das Modell wird als Artefakt im AI Core Workspace bereitgestellt und beim Start ins Dateisystem gemountet.

**Beispiel (Python):**
```python
import pickle

model_path = "/app/artifacts/model.pkl"  # Beispielpfad, wie im YAML gemountet
with open(model_path, "rb") as f:
    model = pickle.load(f)
```
**Hinweis:** Der genaue Mount-Pfad wird im AI Core YAML festgelegt – prüfe, wo das Artefakt landet.

**Vergleich:**
- S3: Flexibel, Cloud-Storage, benötigt AWS-Zugangsdaten.
- Gemountetes Artefakt: Kein externer Zugriff, Lifecycle über AI Core, Pfad muss im YAML stimmen.

---

## 5. Abschluss-Checkliste: Von Anpassung bis Produktion

- [x] Mapping in `serverHostingCombined_with_APM_tutorial.py` angepasst und getestet
- [x] Modell trainiert, gespeichert und hochgeladen (AWS S3)
- [x] `.env`/Secrets korrekt und base64-kodiert
- [x] Server lokal erfolgreich getestet (Initialisierung, Polling, Vorhersage)
- [x] Scikit-learn Version in requirements.txt auf 1.5.2 aktualisiert (Kompatibilität mit trainiertem Modell)
- [x] Flask-Server vereinfacht (Gunicorn entfernt, einfache Flask-Implementation)
- [x] Batch-Processing implementiert: Alle Datenpunkte im Polling-Intervall werden analysiert (nicht nur der neueste pro Feature)
- [ ] Docker-Image mit aktueller `main.py` gebaut und gepusht
- [ ] YAML/Pipeline mit Secrets und Ressourcen angepasst
- [ ] Deployment in AI Core durchgeführt
- [ ] Funktionstest in AI Core (Polling, Vorhersage, Alerting, API-Endpoints)

---

**Fazit:**
Das Grundprinzip (Polling, Vorhersage, Alerting) kann für beliebige Predictive-UseCases übernommen werden. Die Anpassung des Mappings, die Modellintegration und die Konfiguration der Hosting-Umgebung sind die zentralen Stellschrauben. Durch die klare Trennung von Datenzugriff, Modell-Logik und Infrastruktur ist der Transfer auf andere Szenarien schnell möglich. Wichtig ist die Anpassung der Indikatoren, die Modellintegration und die Konfiguration der Hosting-Umgebung (Secrets, Ressourcen, Pfade).

---

## Überblick der Kernkomponenten

**serverHostingCombined_with_APM_tutorial.py** (Produktive Hauptdatei)
- Vollständig integrierte Hybrid-Server-Lösung mit Flask API und Monitoring
- Startet die proaktive Monitoring-Schleife, lädt das ML-Modell von AWS S3 und holt regelmäßig neue Sensordaten aus SAP APM
- Führt Vorhersagen durch und erstellt ggf. Alerts bei erkannten Risiken
- Bietet Flask API-Endpoints: `/v2/health`, `/v2/predict`, `/v2/test-alert`, `/v2/test-connectivity`, `/v2/greet`
- Initialisiert Umgebungsvariablen, OAuth-Token-Handling und Netzwerk-Konnektivitätstests
- Optimierte Logging-Ausgabe: Detailliert bei Initialisierung/Fehlern, minimal während Monitoring
- Polling-Intervall von 5 Sekunden (anpassbar über `POLLING_INTERVAL_SECONDS`)
- Einfache Flask-Server-Implementation ohne zusätzliche WSGI-Server

**hybrid_server_with_apm.py** (Entwicklungs-/Backup-Version)
- Alternative Implementation mit identischen Funktionalitäten
- Wird für Entwicklung, Tests und als Backup verwendet

**send_apm_dataset.py**
- Skript zum einmaligen oder wiederholten Hochladen von Test- oder Trainingsdatenpunkten an SAP APM
- Simuliert das Senden von Sensordaten für Tests oder Demonstrationen
- Unterstützt sowohl einzelne als auch kontinuierliche Datenübertragung

---

## Übertrag auf andere UseCases

1. **Indikatoren anpassen:**
   - Passe das Mapping von SAP APM Merkmalen zu ML-Features an.
   - Definiere relevante Sensordaten und Zielgrößen für den neuen UseCase.
2. **Modell laden:**
   - Trainiere ein neues Modell und exportiere es als Pickle- oder anderes Format.
   - Passe ggf. die Feature-Namen und -Reihenfolge an das neue Modell an.
3. **Vorhersage-Logik:**
   - Implementiere die spezifische Logik zur Risikobewertung und ggf. Alert-Erstellung.
4. **API-Endpunkte (optional):**
   - Ergänze oder passe Flask-Endpunkte für spezifische Anforderungen an.

---


