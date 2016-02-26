
# coding: utf-8

#TabulaRazr - specific to calculate  - TABLE Parser
#Infers a table with arbitrary number of columns from reoccuring patterns in text lines
#(c) Alexander Hirner 2016, no redistribution without permission
#Contributions: ____ (refactoring), UI styling (), ....


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
#10) proper logging


from __future__ import print_function
from backend import *
import os
import sys

import json
from flask import Flask, request, redirect, url_for, send_from_directory
from werkzeug import secure_filename
from flask import jsonify, render_template, make_response
import urllib
from urlparse import urlparse

import matplotlib
#Uncomment the line below to prevent runtime error during file processing
matplotlib.use('Agg')

import matplotlib.pyplot as plt

#######

TITLE = "TabulaRazr (XIRR for muni_bonds)"

scripts = [
    "bower_components/jquery/dist/jquery.min.js",
    "bower_components/materialize/dist/js/materialize.js"
]
css = [
    "./css/main.css",
    "./css/style.css",
    "bower_components/materialize/dist/css/materialize.css"
]

UPLOAD_FOLDER = './static/ug'
ALLOWED_EXTENSIONS = set(['txt', 'pdf'])

TITLE = "TabulaRazr"
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER



def get_extension(filename):
    return '.' in filename and filename.rsplit('.', 1)[1] 

def allowed_file(filename):
    return get_extension(filename) in ALLOWED_EXTENSIONS

def create_path(path):
    try: 
        os.makedirs(path) 
    except OSError:
        if not os.path.isdir(path):
            raise  

@app.route('/', methods=['GET', 'POST'])
def upload_file():

    if request.method == 'POST':
        
        file = request.files['file']
        project = request.form['project']
        url = request.form['url']
        path = os.path.join(app.config['UPLOAD_FOLDER'], project)
        
        filename = None
        
        if url:
            url_fragments = urlparse(url)
            filename_temp = url_fragments.path.split(r'/')[-1]
            if url_fragments.scheme in ('http', 'ftp') and path and allowed_file(filename_temp):
                filename = secure_filename(filename_temp)
                create_path(path)
                path = os.path.join(path, filename)
                urllib.urlretrieve (url, path)
        
        elif file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            create_path(path)
            
            path = os.path.join(path, filename)
            file.save(path)
        
        if filename:
            return redirect(url_for('analyze', project=project, filename=filename))

    return render_template('index.html',
        title=TITLE,
        css=css)


def analyze_file(filename, project):
    
    if not project or project in ("/", "-"):
        project = ""  
        
    path = os.path.join(app.config['UPLOAD_FOLDER'], project, filename)
    extension = get_extension(filename)
    
    txt_path = path
    if extension == "pdf":
        txt_path += '.txt'
        filename += '.txt'        
        if not os.path.isfile(txt_path):
            #Layout preservation crucial to preserve clues about tabular data
            cmd = "pdftotext -enc UTF-8 -layout %s %s " % (path, txt_path)
            os.system(cmd)     
    
    if not os.path.isfile(txt_path):
        return None, filename, jsonify({'error' : txt_path+' not found' })

    #Export tables    
    tables = return_tables(txt_path)

    with codecs.open(txt_path + '.tables.json', "w", "utf-8") as file:
        json.dump(tables, file)

    #Export chart
    lines_per_page = 80
    nr_data_rows = []
    #for t in tables.values():
    #    print t
    for key, t in tables.iteritems():
        e = t['end_line']
        b = t['begin_line']
        for l in range(b, e):
            page = l / lines_per_page
            if len(nr_data_rows) <= page:
                nr_data_rows += ([0]*(page-len(nr_data_rows)+1))
            nr_data_rows[page] += 1
    dr = pd.DataFrame()
    dr['value'] = nr_data_rows
    dr['page'] = range(0, len(dr))
    
    #plot the row density
    chart = filename+".png"
    fig, ax = plt.subplots( nrows=1, ncols=1, figsize=(7,2.5) )  # create figure & 1 axis
    ax.set_xlabel('page nr.')
    ax.set_ylabel('number of data rows')
    ax.set_title('Distribution of Rows with Data')
    ax.plot(dr['page'], dr['value'], )
    fig.savefig(txt_path + '.png')   # save the figure to file
    plt.close(fig)                      # close the figure    

    return tables, filename,  None
    
#Todo: accetpt URLs
@app.route('/analyze/<project>/<filename>', methods=['GET', 'POST'])
def analyze(filename, project):   

    tables, filename_new, error = analyze_file(filename, project)
    if error:
        return error
    
    if request.method == 'POST':
        return jsonify(tables)
    
    return redirect(url_for('show_one_file', filename=filename_new, project=project))
    

#Todo: factor out table rendering, overview etc., i.e. make functions more composable
@app.route('/show/<project>/<filename>')
def show_one_file(filename, project):

    if not project or project in ("/", "-"):
        project = ""   
    path = os.path.join(app.config['UPLOAD_FOLDER'], project, filename)
    
    tables_path = path + '.tables.json'
    chart_path_html = os.path.join('ug', project, filename + '.png')
    if not os.path.isfile(tables_path):
        analyze(filename, project)

    with codecs.open(tables_path, "r", "utf-8") as file:
        tables = json.load(file)   
    #Todo: actually do the filtering
    filter_arg = request.args.get('filter_arg')
        
    #Create HTML
    notices = ['Extraction Results for ' + filename, 'Ordered by lines', 'Applied filter: %s' % filter_arg]    
    dfs = (table_to_df(table).to_html() for table in tables.values())
    
    headers = []
    for t in tables.values():
        if 'headers' in t:
            headers.append(" | ".join(h for h in t['headers']))
        else:
            headers.append('NO HEADER')
    meta_data = [{'begin_line' : t['begin_line'], 'end_line' : t['end_line']} for t in tables.values()]

    return render_template('viewer.html',
        title=TITLE + ' - ' + filename,
        base_scripts=scripts, filename=filename, project=project,
        css=css, notices = notices, tables = dfs, headers=headers, meta_data=meta_data, chart=chart_path_html)

@app.route('/inspector/<project>/<filename>')
def inspector(filename, project):
    if not project or project in ("/", "-"):
        project = ""   
    path = os.path.join(app.config['UPLOAD_FOLDER'], project, filename)
    
    begin_line = int(request.args.get('data_begin'))
    end_line = int(request.args.get('data_end'))
    margin_top = config["meta_info_lines_above"]
    margin_bottom = margin_top
    
    #Todo: solve overlap as in more advanced branches
    notices = ['showing data lines from %i to %i with %i meta-lines above and below' % (begin_line, end_line, margin_top)]
    with codecs.open(path, "r", "utf-8", errors="replace") as file:
        lines = [l.encode("utf-8", errors="replace") for l in file][begin_line - margin_top:end_line + margin_bottom]
        top_lines = lines[:margin_top]
        table_lines = lines[margin_top:margin_top+end_line-begin_line]
        bottom_lines = lines[margin_top+end_line-begin_line:]
    
    offset = begin_line-margin_top
    table_id = begin_line
    
    return render_template('inspector.html',
        title=TITLE,
        base_scripts=scripts, css=css, notices = notices, filename=filename, top_lines=top_lines, project=project,
        table_lines=table_lines, bottom_lines=bottom_lines, offset=offset, table_id=begin_line)

@app.route('/project_analysis', methods=['POST'])
def project_analysis():
    project = request.form['project']    
    if not project or project in ("/", "-"):
        project = ""  
    filter_arg = request.form['filter']
    return redirect(url_for('filter_tables_web', project=project, filter=filter_arg))

@app.route('/filter_tables/<project>', methods=['GET', 'POST'])
def filter_tables_web(project):
    if not project or project in ("/", "-"):
        project = ""   
    path = os.path.join(app.config['UPLOAD_FOLDER'], project)   
    
    filter_arg = request.args.get('filter')
    filter_file = os.path.join('static', 'filters', filter_arg +'.json')
    with codecs.open(filter_file, "r", "utf-8", errors="replace") as file:
        _filter = json.load(file)

    #Go through all .txt files in the project, grab tables and return filtered result
    files = os.listdir(path)
    results = {}
    files_analyzed = set()
    nr_tables = 0
    for i,f in enumerate(files):

        extension = get_extension(f)
        tables_path = path + '.json' 

        if extension == "txt":
            
            tables = None
            if not os.path.isfile(tables_path):
                #Analyze on the spot:
                tables, f_new, error = analyze_file(f, project)
                print ("on the spot", f_new, project, tables_path, error, len(tables))
                if error:
                    return error
            else:
                with codecs.open(tables_path, "r", "utf-8") as file:
                    tables = json.load(file)
                    files_analyzed.update(f)
                
            #Only keep highest results
            for t in filter_tables(tables.values(), _filter):
                if f not in results:
                    results[f] = [t]
                else:
                    max_c = max(r[0] for r in results[f])
                    if t[0] >= max_c:
                        results[f].append(t)
            nr_tables += len(tables)
            #Keep all results
            #results[f] = [t for t in filter_tables(tables.values(), _filter)]
    
    #return jsonify(results)
    #Todo: create .csv for download
    for filename, extracted_results in results.iteritems():
        for result in extracted_results:
            t_html = table_to_df(result[1]).to_html()
            result[1]['html'] = t_html
    
    total_best_tables = sum(len(results[r]) for r in results.keys())
    notices = ["Project %s filtered by %s" % (project, filter_arg), 
               "Total of %i tables exist in %i files" % (nr_tables, len(files_analyzed)),
               "%i best tables across %i files" % (total_best_tables, len(results)) ]
    
    return render_template('filtered_project.html',
        title=TITLE + ' - ' + project + ' filtered by ' + filter_arg,
        base_scripts=scripts, project=project,
        css=css, notices = notices, results=results)

from xirr_calc import xirr

@app.route('/calculate_xirr/<project>/<filename>')
def calculate_xirr(filename, project):

    if not project or project in ("/", "-"):
        project = ""   
    path = os.path.join(app.config['UPLOAD_FOLDER'], project, filename)
    tables_path = path + '.tables.json'
    
    if not os.path.isfile(tables_path):
        analyze(filename, project)

    with codecs.open(tables_path, "r", "utf-8") as file:
        tables = json.load(file)
        
    results = {"funds" : [], "maturity_schedule" : [] }
    
    for k, filter_results in results.iteritems():
        
        filter_file = os.path.join('static', 'filters', k+'.json')
        with codecs.open(filter_file, "r", "utf-8", errors="replace") as file:
            _filter = json.load(file)        
        
        #Only keep highest results
        for t in filter_tables(tables.values(), _filter):
            if len(filter_results) == 0 or t[0] >= max(r[0] for r in filter_results):
                filter_results.append(t)
                t_html = table_to_df(t[1]).to_html()
                filter_results[-1][1]['html'] = t_html
    
    log = []
    # Get salient tables
    funds_table = max(results['funds'], key = lambda t: t[0])[1]
    schedule_table = max(results['maturity_schedule'], key = lambda t: t[0])[1]
    log.append("Using table %i for funds and table %i for maturity schedule" 
               % (funds_table['begin_line'], schedule_table['begin_line']))

    with codecs.open(path, "r", "utf-8") as file:
        rate, log_list = xirr(file, funds_table, schedule_table)

    log += log_list
    
    if rate: 
        log.append("<h3>Final Rate: <b>\%%%0.2f</b></h3><img src=../../static/scrutiny.png>" % rate) 
        
    return render_template('view_filtered.html',
        title=TITLE + ' - ' + filename + ' XIRR calculator with filters,' + ", ".join(results.keys()), 
        base_scripts=scripts, filename=filename, project=project,
        css=css, notices = log, results=results)

    
def run_from_ipython():
    try:
        __IPYTHON__
        return True
    except NameError:
        return False

if run_from_ipython():
    app.run(host='0.0.0.0', port = 7080)
else:
    PORT = int(os.getenv('PORT', 7081))
    app.run(debug=True, host='0.0.0.0', port = PORT)





