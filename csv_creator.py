import os
import csv
from bs4 import BeautifulSoup
import re


def clean_key(text):
    """
    Cleans text to be used as a dictionary key or CSV header.
    Removes special characters and normalizes spacing.
    """
    # Replace German Umlaute for cleaner keys
    text = text.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    # Remove characters that are not alphanumeric, underscore, or space
    text = re.sub(r'[^\w\s]', '', text)
    # Replace spaces and multiple underscores with a single underscore
    text = re.sub(r'\s+', '_', text)
    text = re.sub(r'__+', '_', text)
    return text.strip('_')


def extract_key_value_pairs(table, prefix=""):
    """
    Extracts key-value pairs from tables where keys are in one row
    and values are in the row directly below.
    """
    data = {}
    rows = table.find_all('tr')
    if len(rows) < 2:
        return data

    for i in range(0, len(rows) - 1, 2):  # Iterate over pairs of rows
        key_row = rows[i]
        value_row = rows[i + 1]

        keys = [th.get_text(strip=True) for th in key_row.find_all('b')]
        values = [td.get_text(strip=True) for td in value_row.find_all('td')]

        for j, key_text in enumerate(keys):
            if j < len(values) and key_text:
                key = clean_key(f"{prefix}_{key_text}")
                data[key] = values[j]
    return data


def parse_report_definitive(html_content, filename):
    """
    Parses the HTML content of a single report file and extracts all data points
    with a robust, structure-aware method.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    report_data = {'Dateiname_Quelle': filename}

    # --- 1. General Info ---
    general_header = soup.find('b', string='Datum des Berichts')
    if general_header:
        table = general_header.find_parent('table')
        report_data.update(extract_key_value_pairs(table, "Allgemein"))

    # --- 2. PA Group Sections ---
    pa_sections = soup.find_all('b', string=re.compile(r'^PA \d+'))
    for pa_header in pa_sections:
        pa_prefix = clean_key(pa_header.get_text(strip=True))

        # --- Konfiguration Section ---
        config_title = pa_header.find_next('br').next_sibling.strip()
        if config_title and 'Konfiguration' in config_title:
            config_table = pa_header.find_next('table', {'width': '797', 'border': '1'})
            if config_table:
                # The actual data is in a nested table
                nested_table = config_table.find('table')
                report_data.update(extract_key_value_pairs(nested_table, f"{pa_prefix}_Konfiguration"))

                # --- Blende (Aperture) Table (special structure) ---
                blende_header = config_table.find('b', string='Blende')
                if blende_header:
                    blende_table = blende_header.find_parent('table')
                    blende_rows = blende_table.find_all('tr')
                    if len(blende_rows) > 1:
                        # Extract headers from the first row of labels
                        blende_headers = [clean_key(b.get_text(strip=True)) for b in blende_rows[0].find_all('b')]
                        # Iterate data rows
                        for row in blende_rows[1:]:
                            cells = row.find_all('td')
                            blende_type = cells[0].get_text(strip=True)
                            if blende_type:  # e.g., 'I', 'A', 'B'
                                for k, header in enumerate(blende_headers[1:]):  # skip first header ('Blende')
                                    if k + 1 < len(cells):
                                        key = f"{pa_prefix}_Blende_{blende_type}_{header}"
                                        report_data[key] = cells[k + 1].get_text(strip=True)

        # --- Berechnung Section ---
        calc_title_tag = soup.find('b', string='Berechnung')
        if calc_title_tag:
            # Find the correct title that belongs to this PA section
            if calc_title_tag.find_previous('b', string=re.compile(r'^PA \d+')) == pa_header:
                calc_table = calc_title_tag.find_next('table')
                # It contains two sub-tables
                for sub_table in calc_table.find_all('table'):
                    report_data.update(extract_key_value_pairs(sub_table, f"{pa_prefix}_Berechnung"))

    # --- 3. Prüfteil & Prüfbereich ---
    part_header = soup.find(string='Prüfteil')
    if part_header:
        table = part_header.find_next('table')
        report_data.update(extract_key_value_pairs(table.find('table'), "Pruefteil"))

    area_header = soup.find(string='Prüfbereich')
    if area_header:
        container_table = area_header.find_next('table')
        # Two tables inside: area itself and encoders
        area_tables = container_table.find_all('table')
        if len(area_tables) > 0:
            report_data.update(extract_key_value_pairs(area_tables[0], "Pruefbereich"))
        if len(area_tables) > 1:
            # This is the Weggeber/Encoder table, which has a different structure
            encoder_rows = area_tables[1].find_all('tr')
            encoder_headers = [clean_key(b.get_text(strip=True)) for b in encoder_rows[0].find_all('b')]
            for row in encoder_rows[1:]:
                cells = row.find_all('td')
                axis = cells[0].get_text(strip=True)
                if axis:
                    for k, header in enumerate(encoder_headers):
                        if k < len(cells):
                            report_data[f"Pruefbereich_Weggeber_{axis}_{header}"] = cells[k].get_text(
                                strip=True).replace('\n', ' ').strip()

    # --- 4. Main Indication Summary Table ---
    main_indications_header = soup.find('b', string='Tabelle')
    if main_indications_header:
        main_table = main_indications_header.find_next_sibling('table').find('table')
        rows = main_table.find_all('tr')
        headers = [clean_key(h.get_text(strip=True)) for h in rows[0].find_all('b')]

        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all('td')]
            if len(cells) < len(headers): continue

            ind_num = cells[1].replace('*', '').strip()
            if not ind_num: continue

            prefix = f"Ind_{ind_num}_Uebersicht"  # Add prefix to distinguish from detail
            for i, header in enumerate(headers):
                report_data[f"{prefix}_{header}"] = cells[i]

    # --- 5. Individual Indication Detail Tables ---
    detail_headers = soup.find_all('h3')
    for header in detail_headers:
        # Find all tables that follow an H3 tag until the next H3
        current_tag = header
        while True:
            current_tag = current_tag.find_next()
            if current_tag is None or current_tag.name == 'h3':
                break  # Stop at the next section
            if current_tag.name == 'table' and current_tag.get('border') == '1':
                # This is a detail table if it contains "Indikation Nr."
                ind_num_label = current_tag.find('b', string='Indikation Nr.')
                if not ind_num_label: continue

                # We have a valid detail table
                detail_data = extract_key_value_pairs(current_tag.find('table'), "Detail")
                ind_num = detail_data.get('Detail_Indikation_Nr')
                if not ind_num: continue

                # Add data with a unique prefix
                for key, value in detail_data.items():
                    report_data[f"Ind_{ind_num}_{key}"] = value

                # Extract the note
                note_label = current_tag.find('b', string='Notizen')
                if note_label:
                    note_cell = note_label.find_parent('tr').find_next_sibling('tr').find('td')
                    if note_cell:
                        report_data[f"Ind_{ind_num}_Notizen"] = note_cell.get_text(strip=True)
                break  # Move to the next H3 section

    return report_data


def convert_htm_to_csv(folder_path, output_csv_path):
    """Main function to find, parse, and write CSV."""
    all_data = []
    all_fieldnames = set()

    print(f"Suche nach .htm/.html-Dateien im Ordner: {folder_path}...")
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(('.htm', '.html')):
            file_path = os.path.join(folder_path, filename)
            print(f"Verarbeite Datei: {filename}")
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                report_data = parse_report_definitive(content, filename)
                if report_data:
                    all_data.append(report_data)
                    all_fieldnames.update(report_data.keys())
            except Exception as e:
                print(f"  Konnte {filename} nicht verarbeiten: {e}")

    if not all_data:
        print("Keine gueltigen Berichtsdaten gefunden.")
        return

    print(f"\nSchreibe {len(all_data)} Berichte in die CSV-Datei: {output_csv_path}")
    sorted_fieldnames = sorted(list(all_fieldnames))

    try:
        with open(output_csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=sorted_fieldnames)
            writer.writeheader()
            writer.writerows(all_data)
        print("\nKonvertierung erfolgreich abgeschlossen!")
        print(f"Die Datei wurde hier gespeichert: {output_csv_path}")
    except Exception as e:
        print(f"FEHLER beim Schreiben der CSV-Datei: {e}")


if __name__ == '__main__':
    report_folder = "/Users/tobilindenau/Programmieren/RHB/RHB - Reports/Htm_Reports"
    output_csv = "/Users/tobilindenau/Programmieren/RHB/konvertierte_berichte_FINAL_v2.csv"
    convert_htm_to_csv(report_folder, output_csv)
else:
    print(f"Fehler: Der angegebene Ordner existiert nicht.")
