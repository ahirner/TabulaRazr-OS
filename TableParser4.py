
# coding: utf-8

# In[6]:

#DocX - TABLE Parser
#Infers a table with arbitrary number of columns from reoccuring patterns in text lines
#(c) Alexander Hirner 2016, no redistribution without permission

#Main assumptions Table identificatin:
#1) each row is either in one line or not a row at all
#2) each column features at least one number (=dollar amount)
#2a) each column features at least one date-like string [for time-series only]
#3) a table exists if rows are in narrow consecutive order and share similarities --> scoring algo [DONE] 
#4) each column is separated by more than x consecutive whitespace indicators (e.g. '  ' or '..')

#Feature List Todo:
#1) Acknowledge footnotes / make lower meta-data available
#2) make delimiter length smartly dependent on number of columns (possible iterative approach)
#3) improve captioning: expand non canonical values in tables [DONE] .. but not to the extent how types match up  --> use this to further
## delineate between caption and headers
#4) UI: parameterize extraction on the show page on the fly
#5) deeper type inference on token level: type complex [DONE], subtype header (centered, capitalized), 
## subtype page nr., type free flow [DONE, need paragraph]
#5a) re
#6) Respect negative values with potential '-' for numerical values
#7)
#8) classify tables with keywords (Muni Bonds) and unsupervised clustering (Hackathon)
#9) Restructure folder and URI around MD5 hash (http://stackoverflow.com/questions/24570066/calculate-md5-from-werkzeug-datastructures-filestorage-without-saving-the-object)


# In[7]:

import re
import os
import codecs
import string
from collections import OrderedDict

config = { "min_delimiter_length" : 4, "min_columns": 2, "min_consecutive_rows" : 3, "max_grace_rows" : 3,
          "caption_assign_tolerance" : 10.0, "meta_info_lines_above" : 8, "threshold_caption_extension" : 0.45,
         "header_good_candidate_length" : 3, "complex_leftover_threshold" : 2, "min_canonical_rows" : 0.2}


# In[8]:

import json
import sys

from flask import Flask, request, redirect, url_for, send_from_directory
from werkzeug import secure_filename

from flask import jsonify, render_template, make_response
import numpy as np
import pandas as pd


# In[51]:

#Regex tester online: https://regex101.com
#Contrast with Basic table parsing capabilities of http://docs.astropy.org/en/latest/io/ascii/index.html

tokenize_pattern = ur"[.]{%i,}|[\ \$]{%i,}|" % ((config['min_delimiter_length'],)*2)
tokenize_pattern = ur"[.\ \$]{%i,}" % (config['min_delimiter_length'],)
footnote_inidicator = ur"[^,_!a-zA-Z0-9.]"

column_pattern = OrderedDict()
#column_pattern['large_num'] = ur"\d{1,3}(,\d{3})*(\.\d+)?"
column_pattern['large_num'] = ur"(([0-9]{1,3})(,\d{3})+(\.[0-9]{2})?)"
column_pattern['small_float'] = ur"[0-9]+\.[0-9]+"
column_pattern['integer'] = ur"^\s*[0-9]+\s*$"
#column_patter['delimiter'] = "[_=]{6,}"
#column_pattern['other'] = ur"([a-zA-Z0-9]{2,}\w)"
column_pattern['other'] = ur".+"

subtype_indicator = OrderedDict()
subtype_indicator['dollar'] = ur".*\$.*"
subtype_indicator['rate'] = ur"[%]"
#enter full set of date patterns here if we want refinement early on
subtype_indicator['year'] = ur"(20[0-9]{2})|(19[0-9]{2})"


# In[52]:

#import dateutil.parser as date_parser
#Implement footnote from levtovers
def tag_token(token, ws):
    for t, p in column_pattern.iteritems():
        result = re.search(p, token)
        if result:
            leftover = token[:result.start()], token[result.end():]
            lr = "".join(leftover)
            value = token[result.start():result.end()]
            
            if len(lr) >= config['complex_leftover_threshold']:
                return "complex", "unknown", token, leftover
            
            subtype = "none"
            #First match on left-overs
            for sub, indicator in subtype_indicator.iteritems():
                if re.match(indicator, lr): subtype = sub
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
    matches = re.finditer(tokenize_pattern, line)
    start_end = [ (match.start(), match.end()) for match in matches]
    #No delimiter found so it's free flow text
    if len(start_end) < 1:
        if len(line) == 0:
            return []
        else:
            return [{'start' : 0, 'value' : line, 'type' : 'freeform', 'subtype' : 'none'}]
    
    tokens = re.split(tokenize_pattern, line)
    if tokens[0] == "": 
        tokens = tokens[1:]
    else:
        start_end = [(0,0)] + start_end
    
    features = []
    for se, token in zip(start_end, tokens):
        t, subtype, value, leftover = tag_token(token, line[se[0]:se[1]])
        feature = {"start" : se[1], "value" : value, "type" : t, "subtype" : subtype, "leftover" : leftover}
        features.append(feature)
    return features


# In[66]:

#Establish whether amount of rows is above a certain threshold and whether there is at least one number
def row_qualifies(row):
    return len(row) >= config['min_columns'] and sum( 1 if c['type'] in ['large_num', 'small_float', 'integer'] else 0 for c in row) > 0

def row_equal_types(row1, row2):
    same_types = sum (map(lambda t: 1 if t[0]==t[1] else 0, ((c1['type'], c2['type']) for c1, c2 in zip(row1, row2))))
    return same_types


# In[67]:

#Non qualified rows arm for consistency check but are tolerated for max_grace_rows (whitespace, breakline, junk)
def filter_row_spans_new(row_features, row_qualifies=row_qualifies, ):    

    min_consecutive = config["min_consecutive_rows"]
    grace_rows = config['max_grace_rows']

    last_qualified = None    
    consecutive = 0
    underqualified = 0
    consistency_check = False
    i = 0
    for j, row in enumerate(row_features):
        
        qualifies = row_qualifies(row)
        if consistency_check:
            if not row_type_check(row_features[last_qualified], row):
                qualifies = False
            consistency_check = False
        #print qualifies, row_to_string(row)
        
        if qualifies:
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
                underqualified = 0
                consistency_check = False
            else:
                if last_qualified: 
                    print "BENCHMARKING AGAINST:", row_to_string(row_features[last_qualified], 'type')
                    consistency_check = True
        i += 1
        
    if consecutive >= min_consecutive:
        yield last_qualified, i-underqualified
        
def row_to_string(row, key='value', sep='|'):
    return sep.join(c[key] for c in row)

def row_type_compatible(row_canonical, row_test):
    #Test whether to break because types differ too much
    no_fit = 0
    for c in row_test:
        dist = (abs(c['start']-lc['start']) for lc in row_canonical)
        val, idx = min((val, idx) for (idx, val) in enumerate(dist))
        if c['type'] != row_canonical[idx]['type']:
            no_fit += 1

    fraction_no_fit = no_fit / float(len(row_test))
    #print "test row", row_to_string(row_test), ") against types (", row_to_string(row_canonical, 'type'), ") has %f unmatching types" % fraction_no_fit    
    return fraction_no_fit < config["threshold_caption_extension"]

def filter_row_spans(row_features, row_qualifies):    

    min_consecutive = config["min_consecutive_rows"]
    grace_rows = config['max_grace_rows']

    last_qualified = None    
    consecutive = 0
    underqualified = 0
    underqualified_rows = [] #Tuples of row number and the row    
    
    i = 0
    
    for j, row in enumerate(row_features):
        if row_qualifies(row):
            underqualified = 0
            if last_qualified is None:
                last_qualified = i
                consecutive = 1
            else:
                consecutive += 1    
        else:
            underqualified += 1
            underqualified_rows.append((j, row) )
            if underqualified > grace_rows:
                if consecutive >= min_consecutive:
                    yield last_qualified, i-underqualified+1

                last_qualified = None
                consecutive = 0
                underqualified = 0
        #print i, underqualified, last_qualified, consecutive#, "" or row
        i += 1
        
    if consecutive >= min_consecutive:
        yield last_qualified, i-underqualified


# In[68]:

def row_to_string(row, key='value', sep='|'):
    return sep.join(c[key] for c in row)


# In[82]:

from collections import Counter

def readjust_cols(feature_row, slots):

    feature_new = [{'value' : 'NaN'}] * len(slots)
    for v in feature_row:
        dist = (abs((float(v['start'])) - s) for s in slots)
        val , idx = min((val, idx) for (idx, val) in enumerate(dist))
        if val <= config['caption_assign_tolerance']: feature_new[idx] = v

    return feature_new


def normalize_rows(rows_in, structure):
    slots = [c['start'] for c in structure] 
    nrcols = len(structure)
    
    for r in rows_in:
        if len(r) != nrcols:
            if len(r)/float(nrcols) > config['threshold_caption_extension']:          
                yield readjust_cols(r, slots)
        else:
            yield r

#TODO: make side-effect free
def structure_rows(row_features, meta_features):
    #Determine maximum nr. of columns
    lengths = Counter(len(r) for r in row_features)
    nrcols = config['min_columns']
    for l in sorted(lengths.keys(), reverse=True):
        nr_of_l_rows = lengths[l]
        if nr_of_l_rows/float(len(row_features)) > config['min_canonical_rows']:
            nrcols = l
            break
            
    canonical = filter(lambda r: len(r) == nrcols , row_features)
    
    #for c in canonical: print len(c), row_to_string(c)
        
    structure = []
    for i in range(nrcols):
        col = {}
        col['start'] = float (sum (c[i]['start'] for c in canonical )) / len(canonical)
    
        types = Counter(c[i]['type'] for c in canonical)
        col['type'] = types.most_common(1)[0][0]
        subtypes = Counter(c[i]['subtype'] for c in canonical if c[i]['subtype'] is not "none")        
        subtype = "none" if len(subtypes) == 0 else subtypes.most_common(1)[0][0]
        col['subtype'] = subtype
        structure.append(col)

    #Test how far up the types are compatible and by that are data vs caption
    for r in row_features:
        #if r in canonical:
        if len(r) and row_type_compatible(structure, r):
            break
        else:
            meta_features.append(r)
            row_features.remove(r)
     
    meta_features.reverse()
    #for m in meta_features: print "META", row_to_string(m)
 
    captions = [''] * nrcols
    single_headers = []
    latest_caption_len = 1
    slots = [c['start'] for c in structure] 
    for mf in meta_features:
        #if we have at least two tokens in the line, consider them forming captions
        nr_meta_tokens = len(mf)
        if nr_meta_tokens > 1 and nr_meta_tokens >= latest_caption_len:
            #Find closest match: TODO = allow doubling of captions if it is centered around more than one and len(mf) is at least half of nrcols
            for c in mf:
                dist = (abs((float(c['start'])) - s) for s in slots)
                val, idx = min((val, idx) for (idx, val) in enumerate(dist))
                if val <= config['caption_assign_tolerance']: 
                    captions[idx] = c['value'] + ' ' + captions[idx]
                else: single_headers.append(c['value'])
            #latest_caption_len = nr_meta_tokens
        #otherwise, throw them into headers directly for now                                                                           
        else:
            #Only use single tokens to become headers, throw others away
            if len(mf) == 1: single_headers.append(mf[0]['value'])
    

    #Assign captions as the value in structure
    for i, c in enumerate(captions):
        structure[i]['value'] = c
    #Expand all the non canonical rows with NaN values (Todo: if types are very similar)
    normalized_data = [r for r in normalize_rows(row_features, structure)]            
    
    return structure, normalized_data, single_headers


def convert_to_table(rows, b, e, above):
    table = {'begin_line' : b, 'end_line' : e}

    data_rows = rows[b:e]
    meta_rows = rows[b-above:b]

    structure, data, headers = structure_rows(data_rows, meta_rows)

    captions = [(col['value'] if 'value' in col.keys() else "---") +"\n(%s, %s)" % (col['type'], col['subtype']) for col in structure]
    table['captions'] = captions
    table['data'] = data           
    table['header'] = " | ".join(headers)

    return table 

def indexed_tables_from_rows(row_features):
    
    #Uniquely identify tables by their first row
    tables = OrderedDict()
    last_end = 0
    for b,e in filter_row_spans(row_features, row_qualifies):
        #Slice out the next table and limit the context rows to have no overlaps
        #Todo: manage the lower meta lines
        tables[b] = convert_to_table(row_features, b, e, min(config['meta_info_lines_above'], b - last_end))
        last_end = tables[b]['end_line']
    return tables    
    
def return_tables(txt_path):
    
    #Uniquely identify tables by their first row
    tables = OrderedDict()
    
    with codecs.open(txt_path, "r", "utf-8") as f:
        lines = [l.replace(u'\n', '').replace(u'\r', '') for l in f]
        rows = [row_feature(l) for l in lines] 
        
        return indexed_tables_from_rows(rows)

def table_to_df(table):
    df = pd.DataFrame()
    for i in range(len(table['captions'])):
        values = []
        for r in table['data']:
            values.append(r[i]['value'])
        df[i] = values
    df.columns = table['captions']
    return df


# ## Web App ##

# In[83]:

# TITLE = "TabulaRazr (docX)"

scripts = []
css = [
    "./bower_components/bootstrap/dist/css/bootstrap.min.css",
    "./css/main.css",
    "./css/style.css"
]

import matplotlib.pyplot as plt

UPLOAD_FOLDER = './static/ug'
ALLOWED_EXTENSIONS = set(['txt', 'pdf'])

TITLE = "TabulaRazr"

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
        filename += '.txt'        
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
    fig, ax = plt.subplots( nrows=1, ncols=1, figsize=(8,3) )  # create figure & 1 axis
    ax.set_xlabel('page nr.')
    ax.set_ylabel('number of data rows')
    ax.set_title('Distribution of Rows with Data')
    ax.plot(dr['page'], dr['value'], )
    fig.savefig('./static/ug/'+chart)   # save the figure to file
    plt.close(fig)                      # close the figure

    #Create HTML
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

@app.route('/inspector/<filename>')
def inspector(filename):
    extension = 'txt'
    path = os.path.join(app.config['UPLOAD_FOLDER'], extension, filename)
    begin_line = int(request.args.get('data_begin'))
    end_line = int(request.args.get('data_end'))
    margin_top = config["meta_info_lines_above"]
    margin_bottom = margin_top
    
    notices = ['showing data lines from %i to %i with %i meta-lines above and below' % (begin_line, end_line, margin_top)]
    with codecs.open(path, "r", "utf-8") as file:
        lines = [l.encode('utf-8') for l in file][begin_line - margin_top:end_line + margin_bottom]
        top_lines = lines[:margin_top]
        table_lines = lines[margin_top:margin_top+end_line-begin_line]
        bottom_lines = lines[margin_top+end_line-begin_line:]
    
    offset = begin_line-margin_top
    table_id = begin_line
    
    return render_template('inspector.html',
        title=TITLE,
        base_scripts=scripts, css=css, notices = notices, filename=filename, top_lines=top_lines, 
        table_lines=table_lines, bottom_lines=bottom_lines, offset=offset, table_id=begin_line)


# In[84]:

def run_from_ipython():
    try:
        __IPYTHON__
        return True
    except NameError:
        return False

if run_from_ipython():
    app.run(host='0.0.0.0', port = 7080) #Borrow Zeppelin port for now
else:
    app.run(debug=True, host='0.0.0.0', port = 80)


# 
# ## Tests ##

# In[ ]:

test_string = u"""
   9

                                                 CITY OF OAKLAND
                        Management’s Discussion and Analysis (unaudited) (continued)
                                        Year Ended June 30, 2015


The following table indicates the changes in net position for governmental and business-type activities:

                                                 Statement of Activities
                                       For the Years Ended June 30, 2015 and 2014
                                                      (In Thousands)
                                                Governmental                 Business-Type
                                                  Activitie s                  Activities                         Total
                                               2015           2014          2015        2014               2015           2014
Reve nue s:
Program revenues:
  Charges for services                    $     182,293     $ 152,674   $    57,839    $    53,449    $     240,132     $ 206,123
  Operating grants and contributions             92,865       119,063             -              -           92,865       119,063
  Capital grants and contributions               70,322        42,148             -              -           70,322        42,148
General revenues:
  Property taxes                                267,534       240,779             -              -          267,534        240,779
    State taxes:
    Sales and use taxes                          63,895        58,912             -              -           63,895         58,912
    Gas tax                                      12,030        13,085             -              -           12,030         13,085
  Local taxes:
    Business license                             66,677        62,905             -              -           66,677         62,905
    Utility consumption                          50,594        50,422             -              -           50,594         50,422
    Real estate transfer                         62,665        59,060             -              -           62,665         59,060
    Transient occupancy                 6         21,569        18,468             -              -           21,569         18,468
    Parking                                      18,398        16,661             -              -           18,398         16,661
    Voter approved special tax                   37,443        38,835             -              -           37,443         38,835
    Franchise                                    18,150        16,666             -              -           18,150         16,666
  Interest and investment income                  6,362         6,653           142            165            6,504          6,818
  Other                                          12,745        19,671             -              -           12,745         19,671
Total revenues                                  983,542       916,002        57,981         53,614        1,041,523        969,616
Expenses:
 General government               $              82,493        79,806             -              -           82,493         79,806
 Public safety                                  383,904       379,809             -              -          383,904        379,809
 Community Services                             121,740       116,961             -              -          121,740        116,961
 Community & economic development                75,268        83,657             -              -           75,268         83,657
 Public works                                   105,619       109,177             -              -          105,619        109,177
 Interest on long-term debt                      68,033        59,026             -              -           68,033         59,026
 Sewer                                                -             -        36,957         37,306           36,957         37,306
 Parks and recreation                                 -             -           681            855              681            855
Total expenses                                  837,057       828,436        37,638         38,161          874,695        866,597

Change in net position before transfers         146,485        87,566        20,343         15,453          166,828        103,019
Transfers                                         2,002         2,002        (2,002)        (2,002)               -              -
Special Item - Transfer of excess tax
allocation bond                                 107,696        88,309             -              -          107,696         88,309
Change in net position                          256,183       177,877        18,341         13,451          274,524        191,328
Net position at beginning of year               981,818       803,941       196,334        182,883        1,178,152        986,824
Adjustment due to implementation of
GASB Statement No. 68                         (1,506,760)                   (32,236)                      (1,538,996)             -
Net position at end of year               $    (268,759)    $ 981,818   $ 182,439      $ 196,334      $     (86,320)    $ 1,178,152


Governmental activities: Net position for governmental activities, excluding the special item of
$107.7 million from ORSA transfer of excess bond proceeds to the City, decreased by $58.9 million during
fiscal year 2014-15. Total revenue increased by 7.4 percent and expenses increased by 1.0 percent. During
FY 2013-14, revenues increased at a rate of 10.8 percent and expenses increased by 5.6 percent.


""".split(u"\n")


# In[ ]:

from IPython.display import display

rows = [row_feature(l) for l in test_string]

tables = indexed_tables_from_rows(rows)
for b, e in filter_row_spans(rows, row_qualifies):
    print b, row_to_string(rows[b]), " --> \n", e, row_to_string(rows[e])
    for i in range(b,e):
        print i, len(rows[i]), row_to_string(rows[i])

for begin_line, t in tables.iteritems():
    df = table_to_df(t)
    
    for d in t['data']: print row_to_string(d)
    
    for j in range(t['begin_line']-4, t['begin_line']):
        pass
        
    for j in range(t['begin_line'], t['end_line']):
        pass #print len(rows[j]), test_string[j], "|".join([c['type']+'_'+c['subtype'] for c in rows[j]])
    print t['header']
    display(df)


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






""".split(u"\n")


# In[ ]:

#How to split this one? Three distinct tables because different types (but matching)
test_string = u"""
    THE SERIES 2013 BONDS DO NOT CONSTITUTE A DEBT, LIABILITY OR OBLIGATION OF THE STATE OF MICHIGAN AND NEITHER THE FULL FAITH AND
CREDIT NOR THE TAXING POWER OF THE STATE OF MICHIGAN, THE CITY OF FLINT OR ANY AGENCY OR POLITICAL SUBDIVISION THEREOF IS PLEDGED
TO THE PAYMENT OF THE PRINCIPAL OF OR INTEREST ON THE SERIES 2013 BONDS. THE OBLIGATION OF THE CITY OF FLINT TO MAKE PAYMENTS OF
CASH RENTALS IS A SPECIAL, LIMITED OBLIGATION OF THE CITY OF FLINT PAYABLE SOLELY FROM THE NET REVENUES OF THE MEDICAL CENTER. THE
AUTHORITY HAS NO TAXING POWER.
                                                   AMOUNT, MATURITY, INTEREST RATE, PRICE, YIELD AND CUSIP†
                                                                              Series 2013A Bonds
                               $5,580,000      5.000%      Term Bonds due July 1, 2023 Price 104.077% to Yield 4.500%               CUSIP†: 339510BQ1
                               $8,355,000      5.250%      Term Bonds due July 1, 2028 Price 102.796%* to Yield 4.900%              CUSIP†: 339510BR9
                               $8,005,000      5.250%      Term Bonds due July 1, 2039 Price 99.286% to Yield 5.300%                CUSIP†: 339510BT5
                              _____________________
                              * Priced to the call date.
                                                                                 Series 2013B Bonds
                                                                              $12,290,000 Serial Bonds
                                            Maturity                                Interest
                                            (July 1)             Amount               Rate           Price                        CUSIP†
                                              2013               $555,000             5.000%        100.794%                     339511DT1
                                              2015              $1,235,000            5.000%        105.314%                     339511DV6
                                              2018              $5,150,000            3.750%        101.785%                     339511DY0
                                              2019              $2,350,000            4.000%        101.655%                     339511DZ7
                                              2019              $3,000,000            5.000%        107.186%                     339511EA1
                                                                              $24,300,000 Term Bonds
                              $9,790,000      3.500%       Term Bonds due July 1, 2017       Price 101.976% to Yield 3.000%         CUSIP†: 339511DX2
                              $8,560,000      4.750%       Term Bonds due July 1, 2023       Price 102.027% to Yield 4.500%         CUSIP†: 339511EC7
                              $5,950,000      4.750%       Term Bonds due July 1, 2028       Price 97.347% to Yield 5.000%          CUSIP†: 339511ED5
     The Series 2013 Bonds are being offered when, as and if issued and received by the Underwriter, subject to prior sale, withdrawal or modification of the offer
without any notice, and to the approval of legality of the Series 2013 Bonds by Dickinson Wright PLLC, Troy, Michigan, Bond Counsel. Certain legal matters will be
passed upon for the Medical Center by its General Counsel and for the Authority by its disclosure counsel, Miller, Canfield, Paddock and Stone, P.L.C., Ann Arbor,
Michigan. It is expected that the Series 2013A Bonds in definitive form will be available for delivery to the Underwriter through the facilities of DTC on or about
March 14, 2013 and that the Series 2013B Bonds in definitive form will be available for delivery to the Underwriter through the facilities of DTC on or about April 2, 2013.
     This cover page contains certain information for quick reference only. It is not a summary of the Series 2013 Bonds or the security for the Series 2013 Bonds.
Potential investors must read the entire Official Statement, including the Appendices, to obtain information essential to the making of an informed investment decision.

""".split(u"\n")


# In[ ]:

from IPython.display import display

rows = [row_feature(l) for l in test_string]

tables = indexed_tables_from_rows(rows)
for begin_line, t in tables.iteritems():
    df = table_to_df(t)

    for j in range(t['begin_line']-4, t['begin_line']):
        print len(rows[j]), rows[j]
        
    for j, row in enumerate(t['data']):
        print len(rows[t['begin_line'] + j]), rows[t['begin_line'] + j]
    print t['header']
    display(df)


# In[ ]:

test_string


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

