import pandas as pd
import re

def transform_csv_to_ml_long(input_csv_path, output_csv_path):
    """
    Transforms the wide format CSV (konvertierte_berichte_FINAL_v2.csv) 
    to long format (konvertierte_berichte_ML_long.csv) for ML processing.
    
    Each indication (Ind_1, Ind_2, etc.) becomes a separate row with an index.
    """
    
    # Read the input CSV
    print(f"Reading input CSV: {input_csv_path}")
    df = pd.read_csv(input_csv_path)
    
    # Find all indication numbers
    indication_numbers = set()
    for col in df.columns:
        match = re.match(r'Ind_(\d+)(?:\s\*)?_Detail_', col)
        if match:
            indication_numbers.add(int(match.group(1)))
    
    indication_numbers = sorted(indication_numbers)
    print(f"Found indication numbers: {indication_numbers}")
    
    # Initialize list to store transformed rows
    transformed_rows = []
    
    # Define the indication columns that will be in the output (matching original structure)
    indication_columns = ['A', 'DA', 'Gruppe', 'IUmr', 'Imr', 'Kanal', 'SA', 'Scan', 'vPa_A']
    
    # Process each row in the original CSV
    for row_idx, row in df.iterrows():
        print(f"Processing row {row_idx}...")
        
        # For each indication number, check if there's data and create a new row
        for ind_num in indication_numbers:
            # Check if this indication has any data (look for A value)
            a_col_pattern = f'Ind_{ind_num}(?:\\s\*)?_Detail_A'
            a_col = None
            for col in df.columns:
                if re.match(a_col_pattern, col):
                    a_col = col
                    break
            
            if a_col is None or pd.isna(row[a_col]) or row[a_col] == '':
                continue  # Skip indications without data
            
            # Create new row for this indication
            new_row = {}
            new_row['Index'] = row_idx
            new_row['Indikation'] = ind_num
            
            # Map each indication column
            for col_name in indication_columns:
                if col_name == 'Indikation':
                    continue  # Already set above
                
                # Find the corresponding column in the source data
                col_pattern = f'Ind_{ind_num}(?:\\s\*)?_Detail_{col_name}'
                source_col = None
                for col in df.columns:
                    if re.match(col_pattern, col):
                        source_col = col
                        break
                
                if source_col and not pd.isna(row[source_col]):
                    value = row[source_col]
                    # Format values with appropriate units to match original exactly
                    if col_name == 'A':
                        new_row[col_name] = f"{value} %"
                    elif col_name in ['DA', 'SA', 'vPa_A']:
                        if str(value) == '---' or 'mm' in str(value):
                            new_row[col_name] = '--- mm'
                        else:
                            new_row[col_name] = f"{float(value):.2f} mm"
                    elif col_name in ['IUmr', 'Imr']:
                        if str(value) == '---' or 'mm' in str(value):
                            new_row[col_name] = '--- mm'
                        else:
                            new_row[col_name] = f"{float(value):.2f} mm"
                    elif col_name == 'Scan':
                        if str(value) == '---' or 'mm' in str(value):
                            new_row[col_name] = '--- mm'
                        else:
                            new_row[col_name] = f"{float(value):.2f} mm"
                    elif col_name == 'Gruppe':
                        new_row[col_name] = f"{float(value):.1f}"
                    elif col_name == 'Kanal':
                        new_row[col_name] = str(value)
                    else:
                        new_row[col_name] = str(value)
                else:
                    # Handle missing values with appropriate units
                    if col_name == 'A':
                        new_row[col_name] = '--- %'
                    elif col_name in ['DA', 'IUmr', 'Imr', 'SA', 'Scan', 'vPa_A']:
                        new_row[col_name] = '--- mm'
                    else:
                        new_row[col_name] = '---'
            
            # Add the three PA configuration columns
            new_row[' PA_1_rueckwaerts_Konfiguration_Verstaerkung'] = str(row.get('PA_1_rueckwaerts_Konfiguration_Verstaerkung', '---'))
            # Second column uses PA_2_vorwaerts_Blende_I_Hoehe which contains "56.00 mm" values
            blende_value = row.get('PA_2_vorwaerts_Blende_I_Hoehe', '---')
            if blende_value != '---' and not pd.isna(blende_value):
                new_row['PA_2_vorwaerts_Konfiguration_Verstaerkung'] = f"{blende_value} mm"
            else:
                new_row['PA_2_vorwaerts_Konfiguration_Verstaerkung'] = '--- mm'
            # Third column uses the actual PA_2_vorwaerts_Konfiguration_Verstaerkung
            new_row['PA_2_vorwaerts_Konfiguration_Verstaerkung_duplicate'] = str(row.get('PA_2_vorwaerts_Konfiguration_Verstaerkung', '---'))
            
            transformed_rows.append(new_row)
    
    # Create DataFrame from transformed rows
    result_df = pd.DataFrame(transformed_rows)
    
    # Group by indication number to match original file structure
    # Sort by Indikation first, then by original row order to group all rows of same indication together
    result_df = result_df.sort_values(['Indikation']).reset_index(drop=True)
    
    # Re-assign sequential indices after sorting
    result_df['Index'] = range(len(result_df))
    
    # Ensure column order matches the original exactly
    expected_columns = ['Index', 'Indikation', 'A', 'DA', 'Gruppe', 'IUmr', 'Imr', 'Kanal', 'SA', 'Scan', 'vPa_A', ' PA_1_rueckwaerts_Konfiguration_Verstaerkung', 'PA_2_vorwaerts_Konfiguration_Verstaerkung', 'PA_2_vorwaerts_Konfiguration_Verstaerkung_duplicate']
    
    # Reorder columns to match expected order
    result_df = result_df.reindex(columns=expected_columns, fill_value='---')
    
    # Rename the duplicate column to match the original (both columns have same name)
    result_df.columns = ['Index', 'Indikation', 'A', 'DA', 'Gruppe', 'IUmr', 'Imr', 'Kanal', 'SA', 'Scan', 'vPa_A', ' PA_1_rueckwaerts_Konfiguration_Verstaerkung', 'PA_2_vorwaerts_Konfiguration_Verstaerkung', 'PA_2_vorwaerts_Konfiguration_Verstaerkung']
    
    print(f"Generated {len(result_df)} rows")
    
    # Save to CSV
    result_df.to_csv(output_csv_path, index=False)
    print(f"Saved to {output_csv_path}")
    
    print(f"Transformation complete!")
    print(f"Original rows: {len(df)}")
    print(f"Transformed rows: {len(result_df)}")
    print(f"Output saved to: {output_csv_path}")

if __name__ == '__main__':
    input_file = "/Users/tobilindenau/Programmieren/RHB/konvertierte_berichte_FINAL_v2.csv"
    output_file = "/Users/tobilindenau/Programmieren/RHB/konvertierte_berichte_ML_long_new.csv"
    
    transform_csv_to_ml_long(input_file, output_file)
