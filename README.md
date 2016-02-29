# TabulaRazr
**Extract and browse tabular data from legacy financial documents with ease**.

This repository is a partial release from prior work and the Top 5 submission at [DeveloperWeek 2016](http://accelerate.im/projects/362) ([video presentation](https://www.youtube.com/watch?v=Snqul2fJT5c)). The more elaborate version builds semantic links between tables to efficiently compare deals and aggregate otherwise disconnected knowledge from a large collection of documents.

Issues, forks and heavy usage welcome. Distributed under APGL v3.

# Usage
After uploading a `.txt` or `.pdf` document, all identified tables are presented as well as where they occur in the document.
![View on Document](/../xirr-specific/design/screenshot_show_example.png?raw=true "Municipal Bond of Flint")
The screenshot shows a bond used to construct **public buildings in Jurupa's school district**, Riverside County. 
Additional information, such as inferred data types and positional features of table cells are cached in `.json` files on the local filesystem.

Once the data is structured and annotated, it is relatively easy to automatically calculate domain specific key figures. This customized version includes an experimental calculation for the [internal rate of return](http://www.investopedia.com/terms/i/irr.asp) for Municpal Bonds. Often, auxiliary information is surfaced such as unemployment rates which again can be used as a basis to aggregate hidden knowledge.

# Setup and run

    npm install -g bower
    pip install -r requirements.txt
    bower install
    python server.py

Navigate to `http://localhost:7081` and upload an example document (see below).
You may set your PORT variable to other ports than 7081.

# Folder structure
- /templates ... Jinja2 html templates
- /static ... all stylesheets and media goes there
- /static/ug/<project_name> ... user uploaded data and analysis files (graphs, json)

# Example documents

One running instance with Municipal Bonds and other document categories lives at: http://tabularazr.eastus.cloudapp.azure.com:7081

| Document | Category |
|----------|---------:|
|**Municipal Bond of the City of Flint:** [Debt Service Schedule](http://tabularazr.eastus.cloudapp.azure.com:7081/show/muni_bonds/ER544111-ER421289-ER823264.pdf.txt#1581)|Municipal Bond|
|**Deep Learning Paper:** [Empirical Findings](http://tabularazr.eastus.cloudapp.azure.com:7081/show/_other/sentence_entailment_attention_LSTM.pdf.txt)|other|
|**Annual Report Bosch 2014:** [Sales Figures](http://tabularazr.eastus.cloudapp.azure.com:7081/show/business_reports/Bosch_Annual_Report_2014_Financial_Report.pdf.txt#2238)|Business Report|
|**Annual Report Oakland:** [Income per Sector from 2006 to 2010](http://tabularazr.eastus.cloudapp.azure.com:7081/show/muni_bonds/ER544111-ER421289-ER823264.pdf.txt#3533)|(Business) Report|
|**EY's Biotech Report 2015:** [Europe's Top IPOs in 2014](http://tabularazr.eastus.cloudapp.azure.com:7081/show/business_reports/EY-beyond-borders-2015.pdf.txt#2946)|Business Report| 

# Other documents 
Choose any financial document, research paper or annual report to upload yourself. Or browse these sources.

### Example pdfs from public data (municipal bonds, audit reports, finanical reviews)

- http://emma.msrb.org/EP753324-ER508056-ER910760.pdf
- http://emma.msrb.org/EP407966-EP321048-EP717328.pdf
- http://emma.msrb.org/ER544111-ER421289-ER823264.pdf (very high cost of issuance)
- http://emma.msrb.org/MS132788-MS108096-MD209140.pdf  (1997 bond issue)

### Other documents that may be of interest:

- https://treas-secure.state.mi.us/LAFDocSearch/tl41R01.aspx?&lu_id=1349&doc_yr=2015&doc_code=AUD (2015 Audit)
- https://treas-secure.state.mi.us/LAFDocSearch/tl41R01.aspx?&lu_id=1349&doc_yr=2014&doc_code=AUD (2014 Audit)
- http://www.michigan.gov/documents/treasury/Flint-ReviewTeamReport-11-7-11_417437_7.pdf (Review Team Report used to determine that the city faced a financial emergency)
