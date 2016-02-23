# TabulaRazr
Web App to extract and browse through tabular data using Flask.
Issues, forks and heavy usage welcome. Distributed under APGL v3.

# Setup and run

    pip install -r requirements.txt
    python server.py

Navigate to `http://localhost:7081` and upload an example document (see below).
You may set your PORT variable to other ports than 7081.

# Folder structure
- /templates ... Jinja2 template
- /static ... all stylesheets and media goes there
- /static/ug/<project_name> ... user uploaded data and analysis files (graphs, json)

# Example analyzed documents on temporary running instance
- deep learning paper: http://tabularazr.eastus.cloudapp.azure.com:7081/show/sentence_entailment_attention_LSTM.pdf
- Municipal Bond from Flint: http://tabularazr.eastus.cloudapp.azure.com:7081/show/muni_bonds/ER544111-ER421289-ER823264.pdf.txt#425
- Annual Report Bosch 2014: http://tabularazr.eastus.cloudapp.azure.com:7081/show/business_reports/Bosch_Annual_Report_2014_Financial_Report.pdf.txt#2238
- Annual Report Oakland: http://tabularazr.eastus.cloudapp.azure.com:7081/show/business_reports/OAK056920.pdf.txt#1172

# Example public data
Choose any financial document, research paper or annual report to upload yourself.
Or:

## Example raw pdfs online 
- tabularazr.eastus.cloudapp.azure.com:7081/static/ug/muni_bonds/EP753324-ER508056-ER910760.pdf
- tabularazr.eastus.cloudapp.azure.com:7081/static/ug/muni_bonds/ER544111-ER421289-ER823264.pdf
.. etc.

## Example pdfs from public data (municipal bonds, audit reports, finanical reviews)

- http://emma.msrb.org/EP753324-ER508056-ER910760.pdf
- http://emma.msrb.org/EP407966-EP321048-EP717328.pdf
- http://emma.msrb.org/ER544111-ER421289-ER823264.pdf (very high cost of issuance)

- http://emma.msrb.org/MS132788-MS108096-MD209140.pdf  (1997 bond issue)

Other documents that may be of interest:

- https://treas-secure.state.mi.us/LAFDocSearch/tl41R01.aspx?&lu_id=1349&doc_yr=2015&doc_code=AUD (2015 Audit)
- https://treas-secure.state.mi.us/LAFDocSearch/tl41R01.aspx?&lu_id=1349&doc_yr=2014&doc_code=AUD (2014 Audit)

- http://www.michigan.gov/documents/treasury/Flint-ReviewTeamReport-11-7-11_417437_7.pdf (Review Team Report used to determine that the city faced a financial emergency)
