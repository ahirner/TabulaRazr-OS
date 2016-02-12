
# coding: utf-8

# In[1]:

#TABLE Parser
#Infers a table with arbitrary number of columns from reoccuring patterns in text lines

#Main assumptions Table identificatin:
#1) each row is either in one line or not a row at all [DONE]
#2) each column features at least one number (=dollar amount) [MISSING]
#2a) each column features at least one date-like string
#3) a table exists if rows are in narrow consecutive order and share similarities --> scoring algo [DONE] 
#4) each column is separated by more than 2 consecutive whitespace indicators (e.g. '  ' or '..')

#Feature List:
#1) Acknowledge Footnotes / make lower meta-data available
#2) make delimiter length smartly dependent on number of columns (possible iterative approach)
#3) expand non canonical values in tables [DONE] .. but not to the extent how types match up  --> use this to further
## delineate between caption and headers
#4) UI: parameterize extraction on the show page on the fly
#5) more type inference (e.g. date)


# In[2]:

import re
import os
import codecs
import string
from collections import OrderedDict

config = { "min_delimiter_length" : 3, "min_columns": 2, "min_consecutive_rows" : 3, "max_grace_rows" : 2,
          "caption_reorder_tolerance" : 10.0, "meta_info_lines_above" : 8, "aggregate_captions_missing" : 0.45}


# In[3]:

import json
import sys

from flask import Flask, request, redirect, url_for, send_from_directory
from werkzeug import secure_filename

from flask import jsonify, render_template, make_response
import numpy as np
import pandas as pd


# In[4]:

#Regex tester online: https://regex101.com
#Contrast with Basic table parsing capabilities of http://docs.astropy.org/en/latest/io/ascii/index.html

tokenize_pattern = "[.]{%i,}|[\ \$]{%i,}|" % ((config['min_delimiter_length'],)*2)
tokenize_pattern = "[.\ \$]{%i,}" % (config['min_delimiter_length'],)

column_pattern = OrderedDict()
#column_pattern['large_num'] = ur"\d{1,3}(,\d{3})*(\.\d+)?"
column_pattern['large_num'] = ur"(([0-9]{1,3})(,\d{3})+(\.[0-9]{2})?)"
column_pattern['small_float'] = ur"[0-9]+\.[0-9]+"
column_pattern['integer'] = ur"^\s*[0-9]+\s*$"
#column_pattern['other'] = ur"([a-zA-Z0-9]{2,}\w)"
column_pattern['other'] = ur".+"

subtype_indicator = OrderedDict()
subtype_indicator['dollar'] = r".*\$.*"
subtype_indicator['rate'] = r"[%]"
#enter date's here if we want earlier refinement
subtype_indicator['year'] = "(20[0-9]{2})|(19[0-9]{2})"


# In[5]:

#import dateutil.parser as date_parser
def tag_token(token, ws):
    for t, p in column_pattern.iteritems():
        result = re.search(p, token)
        if result:
            leftover = token[:result.start()] + token[result.end():]
            value = token[result.start():result.end()]
            
            #First match on left-overs
            subtype = "none"
            for sub, indicator in subtype_indicator.iteritems():
                if re.match(indicator, leftover): subtype = sub
            #Only if no indicator matched there, try on full token
            if subtype == "none":
                for sub, indicator in subtype_indicator.iteritems():
                    if re.match(indicator, token): subtype = sub                    
            #Only if no indicator matched again, try on whitespace
            if subtype == "none":
                for sub, indicator in subtype_indicator.iteritems():
                    if re.match(indicator, ws): subtype = sub
            #print token, ":", ws, ":", subtype
            
            return t, subtype, value, leftover
    return "unknown", "none", token, ""
    
def row_feature(line):
    features = []
    matches = re.finditer(tokenize_pattern, line)
    start_end = [ (match.start(), match.end()) for match in matches]
    if len(start_end) < 1: 
        return features
    
    tokens = re.split(tokenize_pattern, line)
    if tokens[0] == "": 
        tokens = tokens[1:]
    else:
        start_end = [(0,0)] + start_end
    
    for se, token in zip(start_end, tokens):
        t, subtype, value, _ = tag_token(token, line[se[0]:se[1]])
        feature = {"start" : se[1], "value" : value, "type" : t, "subtype" : subtype}
        features.append(feature)
    return features


# In[6]:

#Establish whether amount of rows is above a certain threshold and whether there is at least one number
def row_qualifies(row):
    return len(row) >= config['min_columns'] and sum( 1 if c['type'] in ['large_num', 'small_float', 'integer'] else 0 for c in row) > 0

def row_equal_types(row1, row2):
    same_types = sum (map(lambda t: 1 if t[0]==t[1] else 0, ((c1['type'], c2['type']) for c1, c2 in zip(row1, row2))))
    return same_types


# In[7]:

def filter_row_spans(row_features, row_qualifies):    

    min_consecutive = config["min_consecutive_rows"]
    grace_rows = config['max_grace_rows']

    last_qualified = None    
    consecutive = 0
    underqualified = 0
    i = 0
    
    for row in row_features:
        if row_qualifies(row):
            underqualified = 0
            if last_qualified is None:
                last_qualified = i
                consecutive = 1
            else:
                consecutive += 1    
        else:
            underqualified += 1
            if underqualified > grace_rows:
                if consecutive >= min_consecutive:
                    yield last_qualified, i-underqualified+1
                    last_qualified = None                
                    consecutive = 0
                else:
                    last_qualified = None
                    consecutive = 0
                underqualified = 0
        #print i, underqualified, last_qualified, consecutive#, "" or row
        i += 1
        
    if consecutive >= min_consecutive:
        yield last_qualified, i-underqualified


# In[8]:

from collections import Counter

def readjust_cols(feature_row, slots):
        feature_new = [{'value' : 'NaN'}] * len(slots)
        for v in feature_row:
            dist = [ abs((float(v['start'])) - s) for s in slots ]
            val , idx = min((val, idx) for (idx, val) in enumerate(dist))
            if val <= config['caption_reorder_tolerance']: feature_new[idx] = v
        return feature_new

def normalize_rows(rows_in, structure):
    
    slots = [c['start'] for c in structure] 
    nrcols = len(structure)
    
    for r in rows_in:
        if len(r) != nrcols:
            if len(r)/float(nrcols) > config['aggregate_captions_missing']:          
                yield readjust_cols(r, slots)
        else:
            yield r

#TODO: make side-effect free
def structure_rows(row_features, meta_features):
    #Determine maximum nr. of columns
    lengths = [len(r) for r in row_features]
    nrcols = max(lengths)
    canonical = filter(lambda r: len(r) == nrcols , row_features)
    
    #print canonical
    
    structure = []
    values = []
    for i in range(nrcols):
        col = {}
        col['start'] = float (sum (c[i]['start'] for c in canonical )) / len(canonical)
    
        types = Counter(c[i]['type'] for c in canonical)
        col['type'] = types.most_common(1)[0][0]
        subtypes = Counter(c[i]['subtype'] for c in canonical if c[i]['subtype'] is not "none")        
        subtype = "none" if len(subtypes) == 0 else subtypes.most_common(1)[0][0]
        col['subtype'] = subtype
        structure.append(col)
    
    #Add the first non canonical rows to the meta_features above data
    for r in row_features:
        if r in canonical:
            break
        else:
            meta_features.append(r)
            row_features.remove(r)
     
    #Try to find caption from first rows above the data, skip one empty row if necessary
    #Todo: make two steps process cleaner and more general --> use type similarity
    if len(meta_features[-1]) == 0: meta_features = meta_features[:-1]
    caption = meta_features[-1] if len(meta_features[-1])/float(nrcols) > config['aggregate_captions_missing'] else None 
    if caption:
        slots = [c['start'] for c in structure] 
        meta_features = meta_features[:-1]              
        if len(caption) != nrcols: caption = readjust_cols(caption, slots)
        if len(meta_features[-1])/float(nrcols) > config['aggregate_captions_missing']:
            caption2 = readjust_cols(meta_features[-1], slots)
            for c,c2 in zip(caption, caption2):
                if c2['value'] != 'NaN':
                    c['value'] = c2['value'] + ' ' + c['value']
            meta_features = meta_features[:-1]
      
        #Assign captions as the value in structure
        for i, c in enumerate(caption):
            structure[i]['value'] = c['value']
    
    headers = []
    for h in meta_features:
        if len(h) == 1:
            headers.append(h[0]['value'])   
    
    #Expand all the non canonical rows with NaN values (Todo: if types are very similar)
    normalized_data = [r for r in normalize_rows(row_features, structure)]            
    
    return structure, normalized_data, headers


# In[9]:

def output_table_html(txt_path):
    out = []
    out.append("--------" + txt_path + "--------")

    with codecs.open(txt_path, "r", "utf-8") as f:

        lines = [l.encode('ascii', 'ignore').replace('\n', '').replace('\r','') for l in f]
        rows = [row_feature(l) for l in lines]

        for b,e in filter_row_spans(rows, row_qualifies):
            out.append("TABLE STARTING FROM LINE %i to %i" % (b,e))
            table = rows[b:e]
            structure, data, headers = structure_rows(table, rows[b-config['meta_info_lines_above']:b])

            for h in headers: out.append(h)
            if caption: 
                out.append("\t".join(caption))
            else:
                out.append('NO COLUMN NAMES DETECTED')

            for f in rows[b:e]:
                cols = "\t|\t".join([col['value']+" (%s, %s)" % (col['type'], col['subtype']) for col in f])
                out.append("%i %s" % (len(f), cols) )
    return out

def return_table(rows):
    for b,e in filter_row_spans(rows, row_qualifies):
        table = {'begin_line' : b, 'end_line' : e}

        data_rows = rows[b:e]
        meta_rows = rows[b-config['meta_info_lines_above']:b]

        structure, data, headers = structure_rows(data_rows, meta_rows)

        #Construct df
        captions = [(col['value'] if 'value' in col.keys() else "---") +"\n(%s, %s)" % (col['type'], col['subtype']) for col in structure]

        table['captions'] = captions
        table['data'] = data           
        table['header'] = " | ".join(headers)

        return table 

def return_tables(txt_path):
    
    #Uniquely identify tables by their first row
    tables = OrderedDict()
    
    with codecs.open(txt_path, "r", "utf-8") as f:
        lines = [l.replace('\n', '').replace('\r', '') for l in f]
        rows = [row_feature(l) for l in lines] 
        
        for b,e in filter_row_spans(rows, row_qualifies):
            table = {'begin_line' : b, 'end_line' : e}
            
            data_rows = rows[b:e]
            meta_rows = rows[b-config['meta_info_lines_above']:b]
            
            structure, data, headers = structure_rows(data_rows, meta_rows)
            
            #Construct df
            captions = [(col['value'] if 'value' in col.keys() else "---") +"\n(%s, %s)" % (col['type'], col['subtype']) for col in structure]
            
            table['captions'] = captions
            table['data'] = data           
            table['header'] = " | ".join(headers)
            
            tables[b] = table
    
    return tables

def table_to_df(table):
    df = pd.DataFrame()

    for i, c in enumerate(table['captions']):
        values = []
        for r in table['data']:
            values.append(r[i]['value'])
        df[c] = values
        
    return df


# ## Web App ##

# In[51]:

TITLE = "docX - Table View"

scripts = [
    "./bower_components/jquery/dist/jquery.min.js",
    "./bower_components/datatables/media/js/jquery.dataTables.js",
    "./bower_components/d3/d3.min.js",
    "./bower_components/metrics-graphics/dist/metricsgraphics.js",
    "./require.min.js",
    "./bower_components/react/react.js",
    "./bower_components/react-bootstrap/react-bootstrap.min.js",
    "./bower_components/pyxley/build/pyxley.js",
]

css = [
    "./bower_components/bootstrap/dist/css/bootstrap.min.css",
    "./bower_components/metrics-graphics/dist/metricsgraphics.css",
    "./bower_components/datatables/media/css/jquery.dataTables.min.css",
    "./css/main.css",
    "./css/style.css"
]

import matplotlib.pyplot as plt

UPLOAD_FOLDER = './'
ALLOWED_EXTENSIONS = set(['txt', 'pdf'])

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_extension(filename):
    return '.' in filename and            filename.rsplit('.', 1)[1] 

def allowed_file(filename):
    return get_extension(filename) in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files['file']
        min_columns = request.form['min_columns']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            extension = get_extension(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], extension, filename))
            return redirect(url_for('uploaded_file',
                                    filename=filename, min_columns=min_columns))

    return render_template('index.html',
        title=TITLE ,
        css=css)

@app.route('/show/<filename>')
def uploaded_file(filename):
    extension = get_extension(filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], extension, filename)
    txt_path = os.path.join(app.config['UPLOAD_FOLDER'], 'txt', filename)
    if extension == "pdf":
        txt_path += '.txt'
        if not os.path.isfile(txt_path):
        #Layout preservation crucial to preserve clues about tabular data
            cmd = "pdftotext -layout %s %s" % (path, txt_path)
            os.system(cmd)
            
    min_columns = request.args.get('min_columns')
    tables = return_tables(txt_path)

    #Construct histogram
    lines_per_page = 80
    nr_data_rows = []
    for b, t in tables.iteritems():
        e = t['end_line']
        #print b, e
        for l in range(b, e):
            page = l / lines_per_page
            if len(nr_data_rows) <= page:
                nr_data_rows += ([0]*(page-len(nr_data_rows)+1))
            nr_data_rows[page] += 1
    dr = pd.DataFrame()
    dr['value'] = nr_data_rows
    dr['page'] = range(0, len(dr))
    
    #plot the row density
    chart = filename+".jpg"
    fig, ax = plt.subplots( nrows=1, ncols=1, figsize=(10,5) )  # create figure & 1 axis
    ax.set_xlabel('page nr.')
    ax.set_ylabel('number of data rows')
    ax.set_title('Distribution of Rows with Data')
    ax.plot(dr['page'], dr['value'], )
    fig.savefig('./static/ug/'+chart)   # save the figure to file
    plt.close(fig)    # close the figure

    notices = ['Extraction Results for ' + filename, 'Ordered by lines']    
    dfs = (table_to_df(table).to_html() for table in tables.values())
    headers = []
    for t in tables.values():
        if 'header' in t:
            headers.append(t['header'])
        else:
            headers.append('-')
    meta_data = [{'begin_line' : t['begin_line'], 'end_line' : t['end_line']} for t in tables.values()]

    return render_template('viewer.html',
        title=TITLE + ' - ' + filename,
        base_scripts=scripts, filename=filename,
        css=css, notices = notices, tables = dfs, headers=headers, meta_data=meta_data, chart='../static/ug/'+chart)


# In[52]:

@app.route('/inspector/<filename>')
def inspector(filename):
    extension = 'txt'
    path = os.path.join(app.config['UPLOAD_FOLDER'], extension, filename)
    begin_line = int(request.args.get('data_begin'))
    end_line = int(request.args.get('data_end'))
    margin_top = config["meta_info_lines_above"]
    margin_bottom = margin_top
    
    notices = ['original view into ' + filename + 'for table @'+str(begin_line)]
    with open(path) as file:
        lines = [l.decode('ascii', 'ignore') for l in file][begin_line - margin_top:end_line + margin_bottom]
        top_lines = lines[:margin_top]
        table_lines = lines[margin_top:margin_top+begin_line-end_line]
        bottom_lines = lines[margin_top+begin_line-end_line:]
    
    offset = begin_line-margin_top
    table_id = begin_line
    
    return render_template('inspector.html',
        title=TITLE,
        base_scripts=scripts, css=css, notices = notices, top_lines=top_lines, filename=filename,
        table_lines=table_lines, bottom_lines=bottom_lines, offset=offset, table_id=begin_line)


# In[ ]:

#app.run(host='0.0.0.0')
app.run(debug=True, host='0.0.0.0', port = 80)


# 
# ## Tests ##

# In[ ]:

for file in os.listdir('txt'):
    
    print ("--------" + file + "--------")
    tables = return_tables('txt/'+file)
    
    #print tables
    
    #Construct histogram
    lines_per_page = 80
    nr_data_rows = []
    for b, t in tables.iteritems():
        e = t['end_line']
        #print b, e
        for l in range(b, e):
            page = l / lines_per_page
            if len(nr_data_rows) <= page:
                nr_data_rows += ([0]*(page-len(nr_data_rows)+1))
            nr_data_rows[page] += 1
    dr = pd.DataFrame()
    dr['value'] = nr_data_rows
    dr['page'] = range(0, len(dr))    
    #print dr.head()

    line_nrs = [('line %i-%i' % (t['begin_line'], t['end_line'])) for t in tables.values() ]
    print line_nrs
    
    for k, table in tables.iteritems():
        df = table_to_df(table)
        #print k, ' !!! ', table['header'], ' -----------------'
        print df.head()


    #print dr

# Make a Button
cols = [c for c in df.columns if c != "Date"]
btn = SelectButton("Data", cols, "Data", "Steps")

# Make a FilterFrame and add the button to the UI
ui.add_filter(btn)

# Now make a FilterFrame for the histogram
hFig = Figure("/mghist/", "myhist")
hFig.layout.set_size(width=450, height=200)
hFig.layout.set_margin(left=40, right=40)
hFig.graphics.animate_on_load()
# Make a histogram with 20 bins
hc = Histogram(sf, hFig, "value", 20, init_params={"Data": "Steps"})
ui.add_chart(hc)

# Let's play with our input
df["Date"] = pd.to_datetime(df["Date"])
df["week"] = df["Date"].apply(lambda x: x.isocalendar()[1])
gf = df.groupby("week").agg({
        "Date": [np.min, np.max],
        "Steps": np.sum,
        "Calories Burned": np.sum,
        "Distance": np.sum
    }).reset_index()
f = lambda x: '_'.join(x) if (len(x[1]) > 0) and x[1] != 'sum' else x[0]
gf.columns = [f(c) for c in gf.columns]
gf = gf.sort_index(by="week", ascending=False)
gf["Date_amin"] = gf["Date_amin"].apply(lambda x: x.strftime("%Y-%m-%d"))
gf["Date_amax"] = gf["Date_amax"].apply(lambda x: x.strftime("%Y-%m-%d"))

cols = OrderedDict([
    ("week", {"label": "Week"}),
    ("Date_amin", {"label": "Start Date"}),
    ("Date_amax", {"label": "End Date"}),
    ("Calories Burned", {"label": "Calories Burned"}),
    ("Steps", {"label": "Steps"}),
    ("Distance", {"label": "Distance (mi)", "format": "%5.2f"})
])

tb = DataTable("mytable", "/mytable/", gf, columns=cols, paging=True, pageLength=5)
ui.add_chart(tb)

sb = ui.render_layout(app, "./static/layout.js")
# In[ ]:

test_string ="""
        The following table sets forth statistical information relating to the Water System during the five
Fiscal Years shown.
                                                 TABLE 1
                                   WATER SYSTEM STATISTICS
                                                                               Fiscal Year Ended June 30
                                                                  2014         2013       2012     2011      2010
Anaheim Population Served ..................................     348,305      346,161   343,793   341,034   336,265
Population Served Outside City (Est.) ...................          8,457        9,000     9,000     9,000     9,000
        Total Population Served ...........................      356,762      355,161   352,793   350,034   345,265

  Total Water Sales (Million Gallons) ...................         20,740       20,465    19,672    19,526    20,488

Capacity (Million Gallons Per Day)
  From MWD Connections ...................................             110       110       110       110       110
  From Water System Wells (Average) ...............                     79        86        88        81        75
        Total Supply Capacity .............................            189       196       198       191       185

   Treatment Plant Capacity ..................................          15        15        15        15        15

Peak Day Distribution (Million Gallons) ...............                82.2      78.7     79.2      87.2      87.2
Average Daily Distribution (Million Gallons) .......                   60.3      58.9     57.3      59.4      56.1
Average Daily Sales Per Capita (Gallons) .............                159.3     157.9    152.8     152.8     162.6
__________________
Source: Anaheim

Existing Facilities

""".decode('ascii', 'ignore').split("\n")


# In[ ]:




# In[ ]:

test_string ="""
                         CALIFORNIA MUNICIPAL FINANCE AUTHORITY
                                   Revenue Bonds, Series 2015-A
                              (City of Anaheim Water System Project)

                                          MATURITY SCHEDULE

                                            $58,205,000 Serial Bonds

  Maturity Date              Principal                Interest
   (October 1)               Amount                     Rate                   Yield                  CUSIP†
       2015                 $ 775,000                 2.000%                   0.100%             13048TTV5
       2016                  1,575,000                2.000                    0.300              13048TTW3
       2017                  1,620,000                3.000                    0.660              13048TTX1
       2018                  1,675,000                4.000                    0.930              13048TTY9
       2019                  2,045,000                5.000                    1.150              13048TTZ6
       2020                  2,155,000                5.000                    1.320              13048TUA9
       2021                  2,250,000                4.000                    1.520              13048TUB7
       2022                  2,610,000                5.000                    1.670              13048TUC5
       2023                  2,730,000                4.000                    1.810              13048TUD3
       2024                  2,875,000                5.000                    1.920              13048TUE1
       2025                  3,025,000                5.000                    2.030(c)           13048TUF8
       2026                  3,190,000                5.000                    2.200(c)           13048TUG6
       2027                  3,355,000                5.000                    2.320(c)           13048TUH4
       2028                  3,520,000                5.000                    2.450(c)           13048TUJ0
       2029                  3,700,000                5.000                    2.520(c)           13048TUK7
       2030                  3,880,000                5.000                    2.600(c)           13048TUL5
       2031                  4,055,000                4.000                    3.140(c)           13048TUM3
       2032                  4,220,000                4.000                    3.190(c)           13048TUN1
       2033                  4,390,000                4.000                    3.230(c)           13048TUP6
       2034                  4,560,000                4.000                    3.270(c)           13048TUQ4

     $24,535,000 4.000% Term Bonds due October 1, 2040 – Yield: 3.400%(c); CUSIP†: 13048TUR2
     $13,145,000 5.250% Term Bonds due October 1, 2045 – Yield: 2.970%(c); CUSIP†: 13048TUS0
          
""".decode('ascii', 'ignore').split("\n")


# In[ ]:

test_string = """


                                       SCHEDULED DEBT SERVICE
        The scheduled debt service for the Bonds is as follows, assuming no optional redemptions prior to maturity:
                               FORESTVILLE UNION SCHOOL DISTRICT
                            General Obligation Bonds (Election of 2010, Series 2012)
                                     Semi-Annual Debt Service Payments

                                                             Compounded         Total Periodic    Total Annual Debt
Period Ending        Principal            Interest             Interest         Debt Service            Service
 Feb. 1, 2013                –              $57,033.85                 –             $57,033.85                –
 Aug. 1, 2013                –               37,331.25                 –              37,331.25          $94,365.10
 Feb. 1, 2014                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2014                –               37,331.25                 –              37,331.25           74,662.50
 Feb. 1, 2015                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2015                –               37,331.25                 –              37,331.25           74,662.50
 Feb. 1, 2016                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2016                –               37,331.25                 –              37,331.25           74,662.50
 Feb. 1, 2017                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2017                –               37,331.25                 –              37,331.25           74,662.50
 Feb. 1, 2018                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2018                –               37,331.25                 –              37,331.25           74,662.50
 Feb. 1, 2019                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2019                –               37,331.25                 –              37,331.25           74,662.50
 Feb. 1, 2020                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2020           $5,725.80            37,331.25            $9,274.20           52,331.25           89,662.50
 Feb. 1, 2021                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2021            5,095.95            37,331.25             9,904.05           52,331.25           89,662.50
 Feb. 1, 2022                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2022            6,047.20            37,331.25            13,952.80           57,331.25           94,662.50
 Feb. 1, 2023                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2023            6,727.50            37,331.25            18,272.50           62,331.25           99,662.50
 Feb. 1, 2024                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2024            7,184.70            37,331.25            22,815.30           67,331.25          104,662.50
 Feb. 1, 2025                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2025            7,460.25            37,331.25            27,539.75           72,331.25          109,662.50
 Feb. 1, 2026                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2026            6,639.50            37,331.25            28,360.50           72,331.25          109,662.50
 Feb. 1, 2027                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2027            7,597.35            37,331.25            37,402.65           82,331.25          119,662.50
 Feb. 1, 2028                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2028            6,761.70            37,331.25            38,238.30           82,331.25          119,662.50
 Feb. 1, 2029                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2029            6,686.50            37,331.25            43,313.50           87,331.25          124,662.50
 Feb. 1, 2030                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2030            6,546.10            37,331.25            48,453.90           92,331.25          129,662.50
 Feb. 1, 2031                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2031            6,885.45            37,331.25            58,114.55          102,331.25          139,662.50
 Feb. 1, 2032                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2032            6,598.90            37,331.25            63,401.10          107,331.25          144,662.50
 Feb. 1, 2033                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2033            6,292.50            37,331.25            68,707.50          112,331.25          149,662.50
 Feb. 1, 2034                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2034            6,346.95            37,331.25            78,653.05          122,331.25          159,662.50
 Feb. 1, 2035                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2035            5,649.10            37,331.25            79,350.90          122,331.25          159,662.50
 Feb. 1, 2036                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2036            5,619.25            37,331.25            89,380.75          132,331.25          169,662.50
 Feb. 1, 2037                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2037           44,881.20            37,331.25           375,118.80          457,331.25          494,662.50
 Feb. 1, 2038                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2038           92,550.60            37,331.25           342,449.40          472,331.25          509,662.50
 Feb. 1, 2039                –               37,331.25                 –              37,331.25                –
 Aug. 1, 2039          287,012.60            37,331.25           167,987.40          492,331.25          529,662.50
 Feb. 1, 2040                –               32,278.13                 –              32,278.13                –
 Aug. 1, 2040          480,000.00            32,278.13                 –             512,278.13          544,556.26
 Feb. 1, 2041                –               22,378.13                 –              22,378.13                –
 Aug. 1, 2041          520,000.00            22,378.13                 –             542,378.13          564,756.26
 Feb. 1, 2042                –               11,653.13                 –              11,653.13                –
 Aug. 1, 2042          565,000.00            11,653.13                 –             576,653.13          588,306.26
 TOTAL               2,099,309.10        $2,168,208.88        $1,620,690.90       $5,888,208.88       $5,888,208.88






""".split("\n")


# In[ ]:

rows = [row_feature(l) for l in test_string]

table = return_table(rows)
df = table_to_df(table)

print df.columns
print df.head(100)


# In[ ]:

test_string


# In[ ]:

for file in os.listdir('txt'):
    
    print ("--------" + file + "--------")
    
    with codecs.open('txt/'+file, "r", "utf-8") as f:
        
        lines = [l.encode('ascii', 'ignore').replace('\n', '') for l in f]
        rows = [row_feature(l) for l in lines]

        for b,e in filter_row_spans(rows, row_qualifies):
            print "TABLE STARTING AT LINE", b
            table = rows[b:e]
            structure, data, headers = structure_rows(table, rows[b-config['meta_info_lines_above']:b])
            print headers
            captions = [(col['value'] if 'value' in col.keys() else "---") +" (%s, %s)" % (col['type'], col['subtype']) for col in structure]
            print captions  
            for r in data:
                cols = [col['value']+" (%s, %s)" % (col['type'], col['subtype']) for col in r]
                print len(cols), cols
            


# In[ ]:

rstr ="""
Population Served Outside City (Est.) ...................          8,457        9,000     9,000     9,000     9,000
        Total Population Served ...........................      356,762      355,161   352,793   350,034   345,265
""".decode('ascii', 'ignore').split("\n")
for r in rstr:
    print "split", re.split(tokenize_pattern, r)
    print "token", [v['value'] for v in row_feature(r)], row_feature(r)


# In[ ]:

#subtype_indicator['test'] = r'.*\$.*'
for sub, indicator in subtype_indicator.iteritems():
    print sub, indicator, re.match(indicator, "  ..........................................................     $  ")

