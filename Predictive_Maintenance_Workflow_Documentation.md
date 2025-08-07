# Predictive Maintenance Workflow Documentation

## Overview

This document provides a comprehensive overview of the predictive maintenance workflow developed for ultrasonic sound data analysis. The workflow consists of three main components: data extraction from HTML reports, data transformation for machine learning, and unsupervised learning analysis for anomaly detection.

## Project Structure

```
RHB/
├── RHB - Reports/
│   └── Htm_Reports/          # Source HTML reports
├── csv_creator.py            # HTML report parser
├── csv_transformer.py        # Data transformation script
├── unsupervised_learning.ipynb  # ML analysis notebook
├── konvertierte_berichte_FINAL_v2.csv      # Wide format data
├── konvertierte_berichte_ML_long.csv       # ML-ready long format data
```

## Workflow Components

### 1. Data Extraction: `csv_creator.py`

**Purpose**: Extracts structured data from HTML ultrasonic inspection reports and compiles them into a comprehensive CSV dataset.

#### Key Features:
- **HTML Parsing**: Uses BeautifulSoup to parse complex nested HTML table structures
- **Robust Data Extraction**: Handles various report formats and missing data gracefully
- **Structured Output**: Creates a wide-format CSV with all relevant inspection parameters

#### Data Extraction Process:
1. **Report Scanning**: Iterates through all HTML files in the reports directory
2. **Structure Analysis**: Identifies and parses different table types:
   - General information tables
   - PA (Phased Array) configuration data
   - Aperture ("Blende") specifications
   - Calculation parameters
   - Individual indication details
3. **Data Cleaning**: Normalizes keys and handles special characters for CSV compatibility
4. **Aggregation**: Combines data from all reports into a single comprehensive dataset

#### Output Format:
- **File**: `konvertierte_berichte_FINAL_v2.csv`
- **Structure**: Wide format with one row per report
- **Columns**: ~50+ columns including PA configurations, measurements, and indication details

### 2. Data Transformation: `csv_transformer.py`

**Purpose**: Transforms the wide-format data into a machine learning-ready long format, isolating key features relevant for predictive maintenance.

#### Key Features:
- **Format Conversion**: Transforms wide format (multiple indications per row) to long format (one indication per row)
- **Feature Isolation**: Focuses on the most relevant parameters for acoustic analysis
- **Data Formatting**: Maintains exact units and formatting for consistency
- **Missing Value Handling**: Properly handles and formats missing data indicators

#### Transformation Process:
1. **Data Loading**: Reads the wide-format CSV from `csv_creator.py`
2. **Indication Extraction**: Identifies and processes individual indication columns (Ind_1, Ind_2, etc.)
3. **Feature Mapping**: Maps wide-format columns to standardized long-format features:
   - **A**: Amplitude measurements (%)
   - **DA**: Distance measurements (mm)
   - **SA**: Sound path measurements (mm)
   - **Scan**: Scan position measurements (mm)
4. **PA Configuration**: Adds PA (Phased Array) configuration columns from source data
5. **Data Validation**: Ensures proper formatting and unit consistency
6. **Output Generation**: Creates ML-ready dataset with proper indexing and sorting

#### Selected Features for ML:
The transformation focuses on four critical parameters for ultrasonic predictive maintenance:

- **A (Amplitude)**: Signal strength indicator - crucial for defect severity assessment
- **DA (Distance)**: Depth measurement - indicates defect location within material
- **SA (Sound Path)**: Total acoustic path - affects signal interpretation
- **Scan**: Position along scan axis - provides spatial context for defects

#### Output Format:
- **File**: `konvertierte_berichte_ML_long.csv`
- **Structure**: Long format with 704 rows (one per indication)
- **Features**: 4 primary ML features + metadata columns

### 3. Unsupervised Learning Analysis: `unsupervised_learning.ipynb`

**Purpose**: Performs comprehensive unsupervised learning analysis to identify patterns and anomalies in the ultrasonic inspection data.

#### Analysis Pipeline:

##### 3.1 Data Preprocessing
```python
# Feature parsing functions handle different data formats
def parse_percent(val):  # Handles percentage values
def parse_mm(val):       # Handles millimeter measurements
def parse_deg(val):      # Handles degree measurements
```

**Key Steps**:
- **Data Loading**: Imports the long-format CSV (704 samples, 4 features)
- **Feature Parsing**: Converts string data with units to numeric values
- **Missing Value Analysis**: Identifies and quantifies missing data
- **Imputation**: Uses mean imputation strategy for missing values

##### 3.2 Feature Selection and Analysis
**Selected Features**:
- `A_parsed`: Amplitude values (2.9% - 250.0%)
- `DA_parsed`: Distance measurements (25.0 - 80.78 mm)
- `SA_parsed`: Sound path measurements (30.52 - 99.78 mm)  
- `Scan_parsed`: Scan positions (0.0 - 350.0 mm)

**Statistical Summary**:
- **Total Samples**: 704 indications
- **Missing Values**: 230 missing values in DA and SA (32.7%)
- **Feature Variance**: All selected features show significant variance, making them suitable for clustering

##### 3.3 Dimensionality Reduction (PCA)
**PCA Results**:
- **PC1**: Explains 62.1% of variance
- **PC2**: Explains 25.6% of variance
- **Cumulative**: PC1+PC2 explain 87.7% of total variance

**Feature Contributions**:
- **PC1**: Dominated by DA_parsed (0.612) and SA_parsed (0.612) - depth/path measurements
- **PC2**: Dominated by Scan_parsed (0.975) - spatial positioning

##### 3.4 Clustering Analysis

**K-Means Clustering**:
- **Optimal Clusters**: 7 (determined by silhouette analysis)
- **Silhouette Score**: 0.850 (excellent cluster separation)
- **Cluster Distribution**: Balanced clusters ranging from 41 to 205 points

**DBSCAN Clustering**:
- **Parameters**: eps=0.5, min_samples=5
- **Silhouette Score**: 0.863 (slightly better than K-Means)
- **Clusters Found**: 9 clusters + 11 noise points
- **Noise Detection**: Identifies 11 potential outliers/anomalies

##### 3.5 Anomaly Detection and Warning System

**Warning Criteria**:
1. **DBSCAN Noise**: Points classified as noise (cluster = -1)
2. **K-Means Distance**: Points with distance > 99.5th percentile from cluster centroid

**Results**:
- **Total Warnings**: 7 indications flagged as potential anomalies
- **DBSCAN Warnings**: 4 indications
- **K-Means Warnings**: 4 indications
- **Output**: Saved to `unsupervised_warnungen.csv` for further investigation

#### Visualization Components:
1. **Feature Distribution Plots**: Show data distribution for each feature
2. **PCA Visualization**: 2D scatter plots of principal components
3. **Clustering Results**: Side-by-side comparison of K-Means and DBSCAN
4. **Anomaly Highlighting**: Visual identification of warning cases

## Technical Implementation Details

### Dependencies
```python
pandas>=1.3.0          # Data manipulation
numpy>=1.20.0          # Numerical computing
scikit-learn>=1.0.0    # Machine learning algorithms
matplotlib>=3.5.0      # Plotting and visualization
seaborn>=0.11.0        # Statistical visualization
beautifulsoup4>=4.10.0 # HTML parsing
```

### Data Flow Architecture
```
HTML Reports → csv_creator.py → Wide Format CSV → csv_transformer.py → Long Format CSV → unsupervised_learning.ipynb → Anomaly Reports
```

### Key Design Decisions

1. **Feature Selection**: Focused on parameters with real variance and domain relevance
2. **Missing Value Strategy**: Mean imputation to preserve data distribution
3. **Clustering Approach**: Dual algorithm comparison (K-Means + DBSCAN) for robust anomaly detection
4. **Dimensionality Reduction**: PCA for visualization while preserving 87.7% of variance
5. **Warning System**: Conservative approach using multiple criteria to minimize false negatives

## Results and Insights

### Clustering Patterns
The analysis revealed distinct patterns in the ultrasonic inspection data:

1. **Depth-Based Clustering**: PC1 separates indications by depth (DA) and sound path (SA)
2. **Position-Based Clustering**: PC2 separates by scan position, indicating spatial patterns
3. **Anomaly Detection**: 7 indications (1% of data) flagged as potential anomalies

### Predictive Maintenance Implications

**Normal Operation Clusters**: 
- Represent typical inspection patterns
- Can be used as baseline for future comparisons
- Enable automated quality assessment

**Anomaly Indications**:
- May represent defects, measurement errors, or unusual conditions
- Require manual inspection and validation
- Can inform maintenance scheduling and priorities

### Model Performance
- **Silhouette Scores**: 0.850-0.863 indicate excellent cluster separation
- **Variance Explained**: 87.7% with just 2 components shows effective dimensionality reduction
- **Anomaly Rate**: 1% detection rate is reasonable for maintenance applications

## Usage Instructions

### Running the Complete Workflow

1. **Data Extraction**:
   ```bash
   python csv_creator.py
   ```
   - Processes HTML reports from `RHB - Reports/Htm_Reports/`
   - Outputs `konvertierte_berichte_FINAL_v2.csv`

2. **Data Transformation**:
   ```bash
   python csv_transformer.py
   ```
   - Transforms wide format to ML-ready long format
   - Outputs `konvertierte_berichte_ML_long.csv`

3. **ML Analysis**:
   ```bash
   jupyter notebook unsupervised_learning.ipynb
   ```
   - Run all cells to perform complete analysis
   - Generates visualizations and `unsupervised_warnungen.csv`

### Interpreting Results

**Warning Indicators**:
- Check `unsupervised_warnungen.csv` for flagged indications
- Cross-reference with original reports for validation
- Consider maintenance actions for persistent anomalies

**Cluster Analysis**:
- Monitor cluster membership changes over time
- Investigate shifts in cluster centroids
- Use for trend analysis and predictive maintenance scheduling

## Future Enhancements

### Potential Improvements
1. **Time Series Analysis**: Incorporate temporal patterns for trend detection
2. **Supervised Learning**: Develop classification models with labeled defect data
3. **Real-time Processing**: Implement streaming analysis for live monitoring
4. **Advanced Anomaly Detection**: Explore isolation forests or autoencoders
5. **Feature Engineering**: Develop domain-specific composite features

### Scalability Considerations
- **Data Volume**: Current approach handles ~700 indications efficiently
- **Feature Expansion**: Architecture supports additional features with minimal changes
- **Performance**: Consider incremental learning for larger datasets

## Conclusion

This predictive maintenance workflow successfully transforms raw HTML inspection reports into actionable insights through systematic data extraction, transformation, and unsupervised learning analysis. The approach provides:

- **Automated Processing**: Reduces manual data handling
- **Pattern Recognition**: Identifies normal operation clusters
- **Anomaly Detection**: Flags potential issues for investigation
- **Scalable Architecture**: Supports future enhancements and larger datasets

The workflow demonstrates the effective application of machine learning techniques to industrial inspection data, providing a foundation for proactive maintenance strategies and quality assurance in ultrasonic testing applications.
