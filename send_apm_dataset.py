import requests
import json
import datetime
import os
import pandas as pd
import time

# --- Configuration ---
# Load environment variables from .env file if it exists
from dotenv import load_dotenv
load_dotenv()

# APM API Configuration
token_url = os.getenv("APM_OAUTH_TOKEN_URL")
client_id = os.getenv("APM_OAUTH_CLIENT_ID")
client_secret = os.getenv("APM_OAUTH_CLIENT_SECRET")
api_url = os.getenv("APM_TIMESERIES_ENDPOINT")
x_api_key = os.getenv("APM_X_API_KEY")

# Additional APM configuration for indicator initialization
APM_INDICATOR_DATA_ENDPOINT = os.getenv("APM_INDICATOR_DATA_ENDPOINT")
APM_EQ_NUMBER = os.getenv("APM_EQ_NUMBER")
APM_EQ_SSID = os.getenv("APM_EQ_SSID")
APM_EQ_TYPE = os.getenv("APM_EQ_TYPE")

# Global variables for caching
current_access_token = None
token_expires_at = 0
indicator_definitions_global = []
char_id_to_name_map_global = {}

# --- Mapping-Logik wie in initialisiere_indikatoren (Feature-Name zu APM-Merkmal-Name) ---
apm_merkmal_to_model_feature_name_map = {
    "FUMP_TRQ_NM": "Torque [Nm]",
    "FUMP_ROT_SPEED_RPM": "Rotational speed [rpm]",
    "FUMP_TOOL_WEAR": "Tool wear [min]",
    "PUMP_TEMPERATURE_DIFFERENCE": "Temperature difference [C]",
    "PUMP_AIR_TEMPERATURE": "Air temperature [C]",
    "PUMP_PROCESS_TEMPERATURE": "Process temperature [C]",
    "PRODUCT_QUALITY": "Type"
}

# Create reverse mapping from model feature names to APM merkmal names
# Note: This script uses merkmal names as IDs since we don't have the actual characteristic IDs
MODEL_FEATURE_NAME_TO_APM_ID = {v: k for k, v in apm_merkmal_to_model_feature_name_map.items()}


def hole_apm_access_token():
    """Holt ein OAuth2 Access Token von SAP APM und nutzt einen Cache."""
    global current_access_token, token_expires_at
    if current_access_token and token_expires_at > (time.time() + 60):
        return current_access_token

    print("INFO: Fordere neues SAP APM Access Token an...")
    payload = {'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': client_secret}
    
    try:
        response = requests.post(token_url, data=payload, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=10)
        response.raise_for_status()
        token_data = response.json()
        current_access_token = token_data['access_token']
        token_expires_at = time.time() + int(token_data['expires_in'])
        print(f"✅ Neues Access Token erhalten.")
        return current_access_token
    except requests.exceptions.RequestException as e:
        print(f"❌ FEHLER bei der Anfrage für das Access Token: {e}")
        current_access_token, token_expires_at = None, 0
        return None

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

    headers = {"Authorization": f"Bearer {access_token}", "x-api-key": x_api_key, "Accept": "application/json"}
    
    filter_query = f"technicalObject_number eq '{APM_EQ_NUMBER}' and technicalObject_SSID eq '{APM_EQ_SSID}' and technicalObject_type eq '{APM_EQ_TYPE}'"
    indicator_params = {
        '$filter': filter_query,
        '$expand': 'characteristics($select=characteristicsName),category,positionDetails'
    }
    
    try:
        response = requests.get(APM_INDICATOR_DATA_ENDPOINT, headers=headers, params=indicator_params, timeout=15)
        response.raise_for_status()
        indicator_definitions_global = response.json().get('value', [])
        
        print("DEBUG: Vollständige Indikator-Definitionen von der API:")
        print(json.dumps(indicator_definitions_global, indent=2))

        if not indicator_definitions_global:
            print("⚠️ WARNUNG: Keine Indikatoren für das angegebene technische Objekt gefunden.")
            return False
        
        char_id_to_name_map_global.clear()
        
        # Extract position ID from the first indicator (all should have the same position)
        if indicator_definitions_global and 'positionDetails' in indicator_definitions_global[0]:
            global position_id_global
            position_id_global = indicator_definitions_global[0]['positionDetails'].get('ID')
            print(f"🔍 DEBUG: Extracted position ID from API: '{position_id_global}'")

        for item in indicator_definitions_global:
            name_from_api = item['characteristics'].get('characteristicsName')
            char_id = item.get('characteristics_characteristicsInternalId')

            if name_from_api in apm_merkmal_to_model_feature_name_map:
                korrekter_modell_name = apm_merkmal_to_model_feature_name_map[name_from_api]
                char_id_to_name_map_global[char_id] = korrekter_modell_name
        
        print(f"✅ {len(char_id_to_name_map_global)} Indikatoren erfolgreich zugeordnet.")
        print("INFO: Finale, korrigierte Zuordnung:", char_id_to_name_map_global)
        print("==========================================================")
        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ FEHLER bei der Initialisierung der Indikatoren (IndicatorService): {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   -> API Antwort: {e.response.text}")
        return False

def main():
    # Startet den Upload-Prozess für den Datensatz zu SAP APM
    print("🚀 Starting dataset upload to SAP APM...")
    
    # Lädt den Datensatz für den Upload
    dataset_path = os.path.join(os.path.dirname(__file__), "../Presentable/predictive_maintenance_full.csv")
    try:
        # Lese den Datensatz aus der CSV-Datei
        df = pd.read_csv(dataset_path)
        print(f"✅ Loaded dataset with {len(df)} rows")
    except Exception as e:
        print(f"❌ Failed to load dataset: {e}")
        return
    
    # Debug: Check if APM_POSITION_ID is loaded
    position_id = os.environ.get("APM_EQ_POSITION_ID")
    print(f"🔍 DEBUG: APM_POSITION_ID = '{position_id}'")
    if not position_id:
        print("⚠️ WARNING: APM_POSITION_ID is not set in environment variables!")
    
    # Initialisiere die Indikatoren und hole die echten characteristic IDs
    print("🔧 Initializing APM indicators...")
    if not initialisiere_indikatoren():
        print("❌ Failed to initialize indicators. Exiting.")
        return
    
    # Fordert ein OAuth2 Access Token vom APM-System an
    print("🔑 Getting access token...")
    access_token = hole_apm_access_token()
    if not access_token:
        print("❌ Failed to get access token. Exiting.")
        return
    
    # Process each row in the dataset
    success_count = 0
    failure_count = 0
    
    # API Headers
    api_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "X-API-Key": x_api_key
    }
    
    print("\n📤 Sending data to APM (one data point every 15 seconds)...")
    
    for idx, row in df.iterrows():
        # Skip the target column if it exists
        if 'Target' in row:
            row = row.drop('Target')
            
        # Create payload for this row
        # Use the position ID extracted from the API instead of environment variable
        payload = {
            "SSID": APM_EQ_SSID,
            "technicalObjectType": APM_EQ_TYPE,
            "technicalObjectNumber": APM_EQ_NUMBER,
            "categoryName": "M",
            "positionID": position_id_global,
            "values": []
        }
        # Hinweis: Die .env Datei muss die entsprechenden Variablen enthalten!
        
        # Add each feature value to the payload using actual characteristic IDs
        # Create reverse mapping from model feature names to characteristic IDs
        model_feature_to_char_id = {v: k for k, v in char_id_to_name_map_global.items()}
        
        for feature_name in apm_merkmal_to_model_feature_name_map.values():
            if feature_name in row and not pd.isna(row[feature_name]) and feature_name in model_feature_to_char_id:
                char_id = model_feature_to_char_id[feature_name]
                payload["values"].append({
                    "characteristicsInternalId": char_id,
                    "value": str(row[feature_name]),
                    "time": datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
                })

        # --- ENDE: Werte hinzufügen ---
        
        # Skip if no valid data points
        if not payload["values"]:
            continue
            
        print(f"\n📤 Sending data point {idx + 1}/{len(df)}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        try:
            # Send data to APM
            response = requests.post(
                api_url,
                headers=api_headers,
                data=json.dumps(payload),
                verify=False  # Only for testing!
            )
            response.raise_for_status()
            print("✅ Data sent successfully!")
            success_count += 1
            
            # Print response if available
            if response.text:
                try:
                    print("Response:", response.json())
                except:
                    print("Response:", response.text)
                    
        except requests.exceptions.HTTPError as err:
            print(f"❌ Error sending data to APM: {err}")
            if hasattr(err, 'response') and err.response is not None:
                print(f"Response: {err.response.text}")
            failure_count += 1
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            failure_count += 1
        
        # Wartet 15 Sekunden, bevor der nächste Datenpunkt gesendet wird (simuliert Echtzeit-Streaming)
        if idx < len(df) - 1:  # Don't wait after the last row
            print("\n⏳ Waiting 15 seconds before sending next data point...")
            time.sleep(15)
    
    # Gibt eine Zusammenfassung des Uploads aus
    print("\n📊 Upload Summary:")
    print(f"✅ Successfully sent: {success_count} rows")
    print(f"❌ Failed to send: {failure_count} rows")
    print(f"📊 Total rows processed: {success_count + failure_count}")
    print("\n✨ Dataset upload completed!")

if __name__ == "__main__":
    main()
