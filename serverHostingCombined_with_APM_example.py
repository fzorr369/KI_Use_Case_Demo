# =============================================================================
# HYBRID SERVER: Flask + Monitoring Loop für aicore
# =============================================================================
import os
import pickle
from flask import Flask, request
import numpy as np
import requests
import json
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import threading

import pandas as pd
import boto3
from botocore.exceptions import ClientError
import gzip
import tempfile
from dotenv import load_dotenv
from dateutil import parser

# =============================================================================
# KONFIGURATION & INITIALISIERUNG
# =============================================================================

load_dotenv(override=True)

app = Flask(__name__)

# --- Laden der Konfiguration aus den Umgebungsvariablen ---
print("Lade Konfiguration aus den Umgebungsvariablen...")
APM_OAUTH_TOKEN_URL = os.environ.get("APM_OAUTH_TOKEN_URL")
APM_OAUTH_CLIENT_ID = os.environ.get("APM_OAUTH_CLIENT_ID")
APM_OAUTH_CLIENT_SECRET = os.environ.get("APM_OAUTH_CLIENT_SECRET")
APM_X_API_KEY = os.environ.get("APM_X_API_KEY")
APM_ALERT_CREATION_ENDPOINT = os.environ.get("APM_ALERT_CREATION_ENDPOINT")

APM_EQ_NUMBER = os.environ.get("APM_EQ_NUMBER")
APM_ALERT_TYPE = os.environ.get("APM_ALERT_TYPE")
APM_EQ_TYPE = os.environ.get("APM_EQ_TYPE")
APM_EQ_SSID = os.environ.get("APM_EQ_SSID")

APM_INDICATOR_DATA_ENDPOINT = os.environ.get("APM_INDICATOR_DATA_ENDPOINT")
APM_TIMESERIES_ENDPOINT = os.environ.get("APM_TIMESERIES_ENDPOINT")
POLLING_INTERVAL_SECONDS = int(os.environ.get("POLLING_INTERVAL_SECONDS", 15))

S3_BUCKET = os.environ.get("S3_BUCKET")
MODEL_KEY = os.environ.get("MODEL_KEY")
AWS_REGION = os.environ.get("AWS_REGION")

# Feature-Namen und Merkmal-Definitionen
APM_MERKMAL_TO_MODEL_FEATURE_MAP = {
    "PRODUCT_QUALITY": "Type",
    "FUMP_ROT_SPEED_RPM": "Rotational speed [rpm]",
    "FUMP_TRQ_NM": "Torque [Nm]",
    "FUMP_TOOL_WEAR": "Tool wear [min]",
    "PUMP_AIR_TEMPERATURE": "Air temperature [C]",
    "PUMP_PROCESS_TEMPERATURE": "Process temperature [C]",
    "PUMP_TEMPERATURE_DIFFERENCE": "Temperature difference [C]"
}

MERKMAL_NAMES = list(APM_MERKMAL_TO_MODEL_FEATURE_MAP.keys())
FEATURE_NAMES = list(APM_MERKMAL_TO_MODEL_FEATURE_MAP.values())

# Globale Variablen
model = None
current_access_token = None
token_expires_at = 0
indicator_definitions_global = []
char_id_to_name_map_global = {}
monitoring_active = False

# =============================================================================
# HILFSFUNKTIONEN (aus ursprünglichem Script)
# =============================================================================

def initialisiere_indikatoren():
    """
    Ruft die Definitionen aller relevanten Indikatoren
    einmalig vom IndicatorService ab und speichert sie global.
    """
    global indicator_definitions_global, char_id_to_name_map_global
    
    print("==========================================================")
    print("INFO: Initialisiere Indikator-Definitionen...")
    
    access_token = hole_apm_access_token()
    if not access_token:
        print("❌ FEHLER: Kein Access Token für die Initialisierung vorhanden.")
        return False

    headers = {"Authorization": f"Bearer {access_token}", "x-api-key": APM_X_API_KEY, "Accept": "application/json"}
    
    # Verwende die korrekte Filter-Struktur wie in der ursprünglichen Tutorial-Datei
    filter_query = f"technicalObject_number eq '{APM_EQ_NUMBER}' and technicalObject_SSID eq '{APM_EQ_SSID}' and technicalObject_type eq '{APM_EQ_TYPE}'"
    indicator_params = {
        '$filter': filter_query,
        '$expand': 'characteristics($select=characteristicsName),category,positionDetails'
    }
    
    try:
        response = requests.get(APM_INDICATOR_DATA_ENDPOINT, headers=headers, params=indicator_params, timeout=15)
        response.raise_for_status()
        indicator_definitions_global = response.json().get('value', [])
        
        # Reduziertes Logging - nur bei Bedarf aktivieren
        # print("DEBUG: Vollständige Indikator-Definitionen von der API:")
        # import json
        # print(json.dumps(indicator_definitions_global, indent=2))
        
        if not indicator_definitions_global:
            print("⚠️ WARNUNG: Keine Indikatoren für das angegebene technische Objekt gefunden.")
            return False
        
        char_id_to_name_map_global.clear()
        
        # Korrekte Mapping-Logik wie in der ursprünglichen Tutorial-Datei
        for item in indicator_definitions_global:
            name_from_api = item['characteristics'].get('characteristicsName')
            char_id = item.get('characteristics_characteristicsInternalId')
            
            if name_from_api in APM_MERKMAL_TO_MODEL_FEATURE_MAP:
                korrekter_modell_name = APM_MERKMAL_TO_MODEL_FEATURE_MAP[name_from_api]
                char_id_to_name_map_global[char_id] = korrekter_modell_name
        
        print(f"✅ {len(char_id_to_name_map_global)} Indikatoren erfolgreich zugeordnet.")
        # print("INFO: Finale, korrigierte Zuordnung:", char_id_to_name_map_global)
        print("==========================================================")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ FEHLER bei der Initialisierung der Indikatoren (IndicatorService): {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   -> API Antwort: {e.response.text}")
        return False
    except Exception as e:
        print(f"❌ UNERWARTETER FEHLER bei Indikator-Initialisierung: {e}")
        return False

# GEÄNDERT: Verwendet den dokumentierten /Measurements Endpunkt mit GET
# HINWEIS: Fügen Sie 'dateutil.parser' zu Ihren Imports hinzu, falls noch nicht geschehen.
# Sie können es mit 'pip install python-dateutil' installieren.
from dateutil import parser

def hole_apm_sensor_daten(from_time_arg):
    """Ruft Sensordaten AB einem bestimmten Zeitstempel ab."""
    global indicator_definitions_global, char_id_to_name_map_global
    print(f"INFO: Rufe APM-Sensordaten ab seit {from_time_arg.isoformat()}...")
    
    if not char_id_to_name_map_global:
        print("❌ FEHLER: Indikator-Zuordnung ist leer. Datenabruf übersprungen.")
        return None, from_time_arg
    
    access_token = hole_apm_access_token()
    if not access_token:
        print("❌ FEHLER: Kein Access Token für Sensordaten-Abruf vorhanden.")
        return None, from_time_arg

    headers = {"Authorization": f"Bearer {access_token}", "x-api-key": APM_X_API_KEY, "Accept": "application/json"}
    
    # Verwende die korrekte OData-Struktur wie in der ursprünglichen Tutorial-Datei
    requests_to_make = {}
    if indicator_definitions_global:
        pos_id = indicator_definitions_global[0].get('positionDetails', {}).get('ID')
        cat_name = indicator_definitions_global[0].get('category', {}).get('name')
        if pos_id and cat_name:
            requests_to_make[(pos_id, cat_name)] = []
    
    input_data = {}
    newest_timestamp_found = from_time_arg
    
    # Zeitbereich: von from_time_arg bis jetzt
    to_time = datetime.now(timezone.utc)
    from_time = from_time_arg
    
    # Zeitstempel für URL-Parameter formatieren (mit URL-Encoding)
    to_time_str = quote(to_time.strftime('%Y-%m-%dT%H:%M:%SZ'))
    from_time_str = quote(from_time.strftime('%Y-%m-%dT%H:%M:%SZ'))
    
    # Durchlaufe alle gefundenen Position/Category-Kombinationen
    for (pos_id, cat_name), _ in requests_to_make.items():
        try:
            # Baue OData-Key wie in der ursprünglichen Tutorial-Datei
            odata_key = f"(SSID='{APM_EQ_SSID}',technicalObjectType='{APM_EQ_TYPE}',technicalObjectNumber='{APM_EQ_NUMBER}',categoryName='{cat_name}',positionID='{pos_id}',fromTime={from_time_str},toTime={to_time_str})"
            full_url = f"{APM_TIMESERIES_ENDPOINT}{odata_key}"
            
            response = requests.get(full_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            measurement_values = response.json().get('values', [])
            if len(measurement_values) > 0:
                print(f"✅ {len(measurement_values)} empfangen")
            
            if not measurement_values:
                continue
            
            # Verarbeite ALLE Messwerte (nicht nur den neuesten pro Merkmal)
            all_data_points = []
            for value_point in measurement_values:
                char_id = value_point.get('characteristicsInternalId')
                timestamp_str = value_point.get('time')
                value = value_point.get('value')
                
                # Den neuesten Zeitstempel in diesem Batch finden und aktualisieren
                current_ts_obj = parser.parse(timestamp_str)
                if current_ts_obj > newest_timestamp_found:
                    newest_timestamp_found = current_ts_obj
                
                # Erstelle einen Datenpunkt für jede Messung
                data_point = {}
                
                # Mappe Charakteristik-ID zu Feature-Name für diesen Datenpunkt
                if char_id in char_id_to_name_map_global:
                    feature_name = char_id_to_name_map_global[char_id]
                    data_point[feature_name] = float(value)
                    data_point['timestamp'] = timestamp_str
                    
                    # Füge diesen Datenpunkt zur Liste hinzu
                    all_data_points.append(data_point)
            
            # Sammle alle Datenpunkte für die spätere Verarbeitung
            input_data['all_points'] = all_data_points
                    
        except requests.exceptions.RequestException as e:
            print(f"❌ FEHLER bei TimeseriesService für Position '{pos_id}': {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"DEBUG: HTTP Status: {e.response.status_code}")
                print(f"DEBUG: API Antwort: {e.response.text[:500]}...")
                print(f"DEBUG: Request URL: {full_url}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            continue
    
    # Prüfe, ob neue Datenpunkte vorhanden sind
    if not input_data or 'all_points' not in input_data or not input_data['all_points']:
        print("ℹ️ Keine neuen Messungen seit dem letzten Abruf.")
        return None, newest_timestamp_found
    
    print(f"📊 {len(input_data['all_points'])} Datenpunkte gesammelt für Analyse")
    
    return input_data, newest_timestamp_found

def lade_modell():
    """Lädt das ML-Modell aus einem AWS S3 Bucket."""
    global model
    try:
        print("INFO: Lade Modell von AWS S3...")
        print(f"DEBUG: S3 Bucket: {S3_BUCKET}, Model Key: {MODEL_KEY}, Region: {AWS_REGION}")
        s3_client = boto3.client('s3', region_name=AWS_REGION)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.gz') as temp_file:
            print(f"DEBUG: Download zu temporärer Datei: {temp_file.name}")
            s3_client.download_file(S3_BUCKET, MODEL_KEY, temp_file.name)
            
            with gzip.open(temp_file.name, 'rb') as gz_file:
                model = pickle.load(gz_file)
            
            os.unlink(temp_file.name)
        
        print("✅ Modell erfolgreich geladen.")
        print(f"DEBUG: Modell-Typ: {type(model)}")
        return True
    except Exception as e:
        print(f"❌ FEHLER beim Laden des Modells: {e}")
        print(f"DEBUG: Detaillierter Fehler: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return False

def hole_apm_access_token():
    """Holt ein OAuth2 Access Token von SAP APM und nutzt einen Cache."""
    global current_access_token, token_expires_at
    
    if current_access_token and time.time() < token_expires_at:
        return current_access_token
    
    print("INFO: Fordere neues SAP APM Access Token an...")
    print(f"DEBUG: OAuth URL: {APM_OAUTH_TOKEN_URL}")
    print(f"DEBUG: Client ID: {APM_OAUTH_CLIENT_ID[:8]}...")
    
    try:
        response = requests.post(APM_OAUTH_TOKEN_URL, data={
            'grant_type': 'client_credentials',
            'client_id': APM_OAUTH_CLIENT_ID,
            'client_secret': APM_OAUTH_CLIENT_SECRET
        }, timeout=10)
        response.raise_for_status()
        
        token_data = response.json()
        current_access_token = token_data['access_token']
        expires_in = token_data.get('expires_in', 3600)
        token_expires_at = time.time() + expires_in - 60
        
        print("✅ Neues Access Token erhalten.")
        print(f"DEBUG: Token gültig für {expires_in} Sekunden")
        return current_access_token
    except Exception as e:
        print(f"❌ FEHLER beim Abrufen des Access Tokens: {e}")
        print(f"DEBUG: Response Status: {getattr(response, 'status_code', 'N/A')}")
        print(f"DEBUG: Response Text: {getattr(response, 'text', 'N/A')[:200]}...")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        current_access_token, token_expires_at = None, 0
        return None

def test_network_connectivity():
    """Testet die Netzwerkverbindung zu APM-Endpunkten."""
    print("\n=== NETZWERK-KONNEKTIVITÄTS-TEST ===")
    
    endpoints_to_test = [
        ("OAuth Token URL", APM_OAUTH_TOKEN_URL),
        ("Alert Creation Endpoint", APM_ALERT_CREATION_ENDPOINT),
        ("Indicator Data Endpoint", APM_INDICATOR_DATA_ENDPOINT),
        ("Timeseries Endpoint", APM_TIMESERIES_ENDPOINT)
    ]
    
    connectivity_results = {}
    
    for name, url in endpoints_to_test:
        if not url:
            print(f"❌ {name}: URL nicht konfiguriert")
            connectivity_results[name] = False
            continue
            
        try:
            print(f"🔍 Teste {name}: {url}")
            # Nur HEAD Request für schnelleren Test
            response = requests.head(url, timeout=10)
            if response.status_code < 500:  # Alles unter 500 ist erreichbar
                print(f"✅ {name}: Erreichbar (Status: {response.status_code})")
                connectivity_results[name] = True
            else:
                print(f"⚠️ {name}: Server-Fehler (Status: {response.status_code})")
                connectivity_results[name] = False
        except requests.exceptions.Timeout:
            print(f"❌ {name}: Timeout - Endpunkt nicht erreichbar")
            connectivity_results[name] = False
        except requests.exceptions.ConnectionError:
            print(f"❌ {name}: Verbindungsfehler - Endpunkt nicht erreichbar")
            connectivity_results[name] = False
        except Exception as e:
            print(f"❌ {name}: Unerwarteter Fehler - {e}")
            connectivity_results[name] = False
    
    print("=== ENDE NETZWERK-TEST ===\n")
    return connectivity_results

def erstelle_apm_alert():
    """Erstellt den Alert in SAP APM mit detailliertem Logging für Debugging."""
    print("\n=== ALERT CREATION DEBUG INFO ===")
    
    # 1. Überprüfe Umgebungsvariablen
    print(f"APM_ALERT_CREATION_ENDPOINT: {APM_ALERT_CREATION_ENDPOINT}")
    print(f"APM_ALERT_TYPE: {APM_ALERT_TYPE}")
    print(f"APM_EQ_NUMBER: {APM_EQ_NUMBER}")
    print(f"APM_EQ_SSID: {APM_EQ_SSID}")
    print(f"APM_EQ_TYPE: {APM_EQ_TYPE}")
    print(f"APM_X_API_KEY: {'***' if APM_X_API_KEY else 'NICHT GESETZT'}")
    
    # Überprüfe kritische Variablen
    missing_vars = []
    if not APM_ALERT_CREATION_ENDPOINT:
        missing_vars.append("APM_ALERT_CREATION_ENDPOINT")
    if not APM_ALERT_TYPE:
        missing_vars.append("APM_ALERT_TYPE")
    if not APM_EQ_NUMBER:
        missing_vars.append("APM_EQ_NUMBER")
    if not APM_X_API_KEY:
        missing_vars.append("APM_X_API_KEY")
        
    if missing_vars:
        print(f"❌ FEHLER: Fehlende Umgebungsvariablen für Alert: {', '.join(missing_vars)}")
        return False
    
    # 2. Access Token holen
    print("\n--- Hole Access Token ---")
    access_token = hole_apm_access_token()
    if not access_token:
        print("❌ FEHLER: Kein Access Token für APM-Alert vorhanden.")
        return False
    print(f"✅ Access Token erhalten (Länge: {len(access_token)})")

    # 3. Request vorbereiten
    headers = {
        "Authorization": f"Bearer {access_token}", 
        "x-api-key": APM_X_API_KEY, 
        "Content-Type": "application/json"
    }
    
    payload = {
        "AlertType": APM_ALERT_TYPE,
        "TriggeredOn": datetime.now(timezone.utc).isoformat(),
        "TechnicalObject": [{"Number": APM_EQ_NUMBER, "SSID": APM_EQ_SSID, "Type": APM_EQ_TYPE}],
        "Source": "ML_Predictive_Maintenance_Server"
    }
    
    print(f"\n--- Request Details ---")
    print(f"URL: {APM_ALERT_CREATION_ENDPOINT}")
    print(f"Headers: {dict((k, '***' if k == 'Authorization' or k == 'x-api-key' else v) for k, v in headers.items())}")
    print(f"Payload: {json.dumps(payload, indent=2)}")

    # 4. Request senden
    try:
        print(f"\n--- Sende Alert an SAP APM ---")
        response = requests.post(
            APM_ALERT_CREATION_ENDPOINT, 
            headers=headers, 
            json=payload, 
            timeout=30
        )
        
        print(f"Response Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200 or response.status_code == 201:
            print(f"✅ Alert erfolgreich erstellt. Status: {response.status_code}")
            try:
                response_json = response.json()
                print(f"Response Body: {json.dumps(response_json, indent=2)}")
            except:
                print(f"Response Body (Text): {response.text}")
            return True
        else:
            print(f"❌ Alert-Erstellung fehlgeschlagen. Status: {response.status_code}")
            print(f"Response Body: {response.text}")
            
            if response.status_code == 401:
                print("   -> DIAGNOSE: Authentifizierungsfehler - Token ungültig oder abgelaufen")
            elif response.status_code == 403:
                print("   -> DIAGNOSE: Autorisierungsfehler - Keine Berechtigung für Alert-Erstellung")
            elif response.status_code == 404:
                print("   -> DIAGNOSE: Endpoint nicht gefunden - URL möglicherweise falsch")
            elif response.status_code == 422:
                print("   -> DIAGNOSE: Ungültige Daten - Payload-Format oder -Inhalt fehlerhaft")
            elif response.status_code >= 500:
                print("   -> DIAGNOSE: Server-Fehler auf APM-Seite")
            
            return False
            
    except requests.exceptions.Timeout as e:
        print(f"❌ TIMEOUT beim Senden des Alerts: {e}")
        print("   -> DIAGNOSE: Netzwerk-Timeout - möglicherweise langsame Verbindung in aicore")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"❌ VERBINDUNGSFEHLER beim Senden des Alerts: {e}")
        print("   -> DIAGNOSE: Kann APM-Endpoint nicht erreichen")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ ALLGEMEINER FEHLER beim Senden des Alerts: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   -> API Antwort Status: {e.response.status_code}")
            print(f"   -> API Antwort Body: {e.response.text}")
        return False
    except Exception as e:
        print(f"❌ UNERWARTETER FEHLER beim Alert-Senden: {type(e).__name__}: {e}")
        import traceback
        print(f"   -> Traceback: {traceback.format_exc()}")
        return False
    finally:
        print("=== END ALERT CREATION DEBUG ===")

def fuehre_vorhersage_aus(sensor_data):
    """Verarbeitet alle Datenpunkte und führt Vorhersagen für jeden aus."""
    if model is None:
        print("❌ FEHLER: Modell ist nicht geladen. Kann keine Vorhersage durchführen.")
        return

    if not sensor_data or 'all_points' not in sensor_data:
        print("❌ FEHLER: Keine Datenpunkte für Vorhersage vorhanden.")
        return
        
    all_data_points = sensor_data['all_points']
    if not all_data_points:
        print("ℹ️ Keine neuen Datenpunkte für Analyse vorhanden.")
        return

    try:
        # Gruppiere Datenpunkte nach Zeitstempel für vollständige Feature-Sets
        timestamp_groups = {}
        for point in all_data_points:
            timestamp = point.get('timestamp')
            if timestamp not in timestamp_groups:
                timestamp_groups[timestamp] = {}
            
            # Füge alle Features dieses Datenpunkts zur Zeitstempel-Gruppe hinzu
            for feature, value in point.items():
                if feature != 'timestamp':
                    timestamp_groups[timestamp][feature] = value
        
        print(f"📊 Analysiere {len(timestamp_groups)} Datenpunkt-Gruppen...")
        
        failure_risk_count = 0
        total_predictions = 0
        
        # Verarbeite jede Zeitstempel-Gruppe separat
        for timestamp, features in timestamp_groups.items():
            # Füge Type-Mapping hinzu
            type_mapping = {'L': 0.0, 'M': 1.0, 'H': 2.0}
            features['Type'] = type_mapping.get(APM_EQ_TYPE, 0.0)
            
            # Stelle sicher, dass alle erforderlichen Features vorhanden sind
            input_data = {}
            for feature in FEATURE_NAMES:
                input_data[feature] = features.get(feature, 0.0)
            
            # Erstelle DataFrame für diesen Datenpunkt
            input_df = pd.DataFrame([input_data], columns=FEATURE_NAMES).fillna(0.0)
            
            # Führe Vorhersage aus
            prediction = model.predict(input_df[FEATURE_NAMES])[0]
            total_predictions += 1
            
            # Prüfe auf Ausfallrisiko (Annahme: 1 = Ausfallrisiko, 0 = Normal)
            if prediction == 1:
                failure_risk_count += 1
                print(f"🔴 Ausfallrisiko erkannt um {timestamp}!")
        
        # Zusammenfassung und Alert-Entscheidung
        if failure_risk_count > 0:
            print(f"⚠️ {failure_risk_count}/{total_predictions} Datenpunkte zeigen Ausfallrisiko! Alert wird erstellt...")
            erstelle_apm_alert()
        else:
            print(f"✅ Kein Ausfallrisiko festgestellt ({total_predictions} Datenpunkte analysiert)")

    except Exception as e:
        print(f"❌ FEHLER bei der Batch-Vorhersage: {e}")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")

# =============================================================================
# FLASK ROUTEN FÜR HEALTH CHECKS UND DEBUGGING
# =============================================================================

@app.route("/v2/greet", methods=["GET"])
def greet():
    """Health Check Endpunkt für aicore."""
    return {
        "message": "Hello, this is the ML server for Predictive Maintenance!",
        "status": "healthy",
        "model_loaded": model is not None,
        "monitoring_active": monitoring_active,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.route("/v2/health", methods=["GET"])
def health():
    """Erweiterte Health Check mit System-Status."""
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "monitoring_active": monitoring_active,
        "environment_check": {
            "apm_oauth_url": bool(APM_OAUTH_TOKEN_URL),
            "apm_alert_endpoint": bool(APM_ALERT_CREATION_ENDPOINT),
            "aws_config": bool(S3_BUCKET and MODEL_KEY),
            "apm_credentials": bool(APM_OAUTH_CLIENT_ID and APM_OAUTH_CLIENT_SECRET)
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.route("/v2/test-connectivity", methods=["GET"])
def test_connectivity():
    """Testet die Netzwerkverbindung zu allen APM-Endpunkten."""
    connectivity_results = test_network_connectivity()
    return {
        "connectivity_test": connectivity_results,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.route("/v2/test-alert", methods=["POST"])
def test_alert():
    """Testet die Alert-Erstellung manuell."""
    try:
        success = erstelle_apm_alert()
        return {
            "alert_test": "success" if success else "failed",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {
            "alert_test": "error",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, 500

@app.route("/v2/predict", methods=["POST"])
def predict():
    """Endpunkt für manuelle Vorhersage-Anfragen."""
    try:
        if model is None:
            return {
                "error": "Modell ist nicht geladen",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }, 500
        
        # Erwarte JSON-Daten im Request
        data = request.get_json()
        if not data:
            return {
                "error": "Keine JSON-Daten im Request gefunden",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }, 400
        
        # Konvertiere zu DataFrame
        input_df = pd.DataFrame([data])
        
        # Prüfe, ob alle erforderlichen Features vorhanden sind
        missing_features = [feature for feature in FEATURE_NAMES if feature not in input_df.columns]
        if missing_features:
            return {
                "error": f"Fehlende Features: {missing_features}",
                "required_features": FEATURE_NAMES,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }, 400
        
        # Führe Vorhersage aus
        prediction = model.predict(input_df[FEATURE_NAMES])[0]
        
        # Bestimme Risiko-Level
        risk_level = "HIGH" if prediction == 1 else "LOW"
        
        return {
            "prediction": int(prediction),
            "risk_level": risk_level,
            "features_used": FEATURE_NAMES,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        return {
            "error": f"Fehler bei der Vorhersage: {str(e)}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, 500

# =============================================================================
# MONITORING SCHLEIFE IN SEPARATEM THREAD
# =============================================================================

def monitoring_loop():
    """Proaktive Monitoring-Schleife läuft permanent im Hintergrund."""
    global monitoring_active
    monitoring_active = True
    
    print(f"INFO: Monitoring gestartet (alle {POLLING_INTERVAL_SECONDS}s)")
    last_processed_timestamp = datetime.now(timezone.utc) - timedelta(seconds=POLLING_INTERVAL_SECONDS)

    while monitoring_active:
        try:
            # Hole echte APM-Sensordaten seit letztem Abruf
            sensor_data, new_timestamp = hole_apm_sensor_daten(last_processed_timestamp)
            
            if sensor_data is not None and len(sensor_data) > 0:
                # Führe Vorhersage-Analyse durch
                fuehre_vorhersage_aus(sensor_data)
                
                # Update timestamp für nächsten Zyklus
                if new_timestamp:
                    last_processed_timestamp = new_timestamp
                else:
                    last_processed_timestamp = datetime.now(timezone.utc)
            else:
                # Update timestamp auch wenn keine Daten gefunden wurden
                if new_timestamp:
                    last_processed_timestamp = new_timestamp
                else:
                    last_processed_timestamp = datetime.now(timezone.utc)
            
            time.sleep(POLLING_INTERVAL_SECONDS)
            
        except Exception as e:
            print(f"❌ FEHLER in Monitoring-Schleife: {e}")
            time.sleep(POLLING_INTERVAL_SECONDS)

# =============================================================================
# HAUPTPROGRAMM
# =============================================================================

if __name__ == '__main__':
    print("🚀 Starte Hybrid Server (Flask + Monitoring)...")
    
    # 1. Modell laden
    model_loaded = lade_modell()
    
    # 2. Indikator-Definitionen initialisieren
    indicators_loaded = initialisiere_indikatoren()
    if not indicators_loaded:
        print("⚠️ Warnung: Indikator-Definitionen konnten nicht geladen werden")
    
    # 3. Netzwerk-Konnektivität testen
    connectivity_results = test_network_connectivity()
    
    # 4. Monitoring-Thread starten (nur wenn Modell geladen)
    if model_loaded:
        monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitoring_thread.start()
        print("✅ Monitoring-Thread gestartet")
    else:
        print("⚠️ Monitoring nicht gestartet - Modell konnte nicht geladen werden")
    
    # 4. Flask-Server starten
    port = int(os.getenv('PORT', 5001))
    print(f"🌐 Starte Flask-Server auf Port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
