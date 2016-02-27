from datetime import date
import dateutil.parser as date_parser

from backend import config
from fuzzywuzzy import fuzz


# Cascades:
# 1) exact
# 2) lower case exact
# 3) lower case contains
# 4) lower case partial ratio (with min_partial_ratio)
# 5) token sorted partial 
# Apply to different dimensions (header, column names, row names)
def fuzzy_str_match(query, string, min_threshold = 0.0):

    score = 1.0
    inv_cascades = config["fuzzy_cascades"]
    
    #1.0
    #print ("exact equals", score)
    if query == string: return score
    score -= inv_cascades
    if score < min_threshold: return None
    
    #0.75
    #print("lower equals", score)
    q_l = query.lower()
    s_l = string.lower()
    if q_l == s_l: return score
    score -= inv_cascades
    if score < min_threshold: return None
    
    #0.5
    #print("lower contains", score)    
    if q_l in s_l : return score
    if score < min_threshold: return None
    
    min_partial_ratio = config["min_fuzzy_ratio"]
    #0.5 - 0.25
    #print("fuzzy_partial", score)   
    #Also penalize short target strings
    penalty = min((len(s_l.strip()) - 1) / float(len(q_l)), 1.0)
    fuzzy_partial = (fuzz.partial_ratio(q_l, s_l)/100.0) * penalty
    if fuzzy_partial > min_partial_ratio:
        f_score = score - (1.0-(fuzzy_partial - min_partial_ratio) / min_partial_ratio) * inv_cascades 
        if f_score < min_threshold: 
            return None
        else:
            return f_score
    score -= inv_cascades
    if score < min_threshold: return None
    
    #0.25 - > 0.
    #print("fuzzy_partial_token", score)
    fuzzy_partial = (fuzz.token_sort_ratio(q_l, s_l)/100.0) * penalty
    if fuzzy_partial > min_partial_ratio:
        f_score = score - (1.0-(fuzzy_partial - min_partial_ratio) / min_partial_ratio) * inv_cascades
        if f_score < min_threshold: 
            return None
    #None
    return None

#Flatmap from tables to sequence of tuples (confidence, table, row or None, value or None)
def filter_tables(tables, filter_dict, treshold = 0.0, only_max = False):
    #only_max = true.. only yields tables when higher than the last table
    row = None
    value = None
    
    for t in tables:

        if 'headers' in filter_dict:
            
            max_conf, index, best_term = None, None, None 
            terms = filter_dict['headers']['terms']
            _threshold = max(treshold, filter_dict['headers']['threshold'])
            for term in terms:
                if t['headers']:
                    current_max_conf = (max_conf if only_max else _threshold) or _threshold
                    scores_indices = ((val, idx) for (idx, val) in enumerate(fuzzy_str_match(term, h, current_max_conf) for h in t['headers'] ) )

                    conf, idx = max(scores_indices)
                
                    if conf > max_conf:
                        max_conf = conf
                        index = idx
                        best_term = term
                        best_header = ""
            
            """
            if max_conf:
                #Todo: other filter criteria like column names, rows etc. and total confidence score
                print ("Table %i qualified best for term %s in header %s with %.2f confidence" %(t['begin_line'],
                                                                                best_term, t['headers'][index], max_conf))
            """
            if max_conf:
                yield max_conf, t, row, value 
                
                
def get_fuzzy_date(string):
    today = date.today()
    v_ascii = string.encode("ascii", errors="ignore")
    try: 
        dt = date_parser.parse(v_ascii, fuzzy=True, default=today)
        if dt != today:
            return dt
    except:
        return None
    
def get_first_date(lines, query_string, threshold = 0.4):
    for i, l in enumerate(lines):
        if fuzzy_str_match(query_string, l) > threshold: 
            dt = get_fuzzy_date(l)
            if dt:
                return dt, i, l
                   
def find_row(table, query_string):
    #Find first 'other' typed row
    try:
        index = table['types'].index('other')
    except ValueError:
        print "no column with mainly string data found"
        return None
    
    strings = (s[index]['value'] for s in table['data'])
    scores_indices = ((val, idx) for (idx, val) in enumerate(fuzzy_str_match(query_string, s) for s in strings ) )
    
    return table['data'][max(scores_indices)[1]]

def find_column(table, query_string, types=None, subtypes=None, threshold = 0.4):
    #Find first column with specific types
    
    columns = []
    for i, t in enumerate(zip(table['types'], table['subtypes'])):
        t, st = t[0], t[1]
        if t in (types or t) and st in (subtypes or st):
            if fuzzy_str_match(query_string, table['captions'][i]) > threshold: return i


def closest_row_numeric_value(table, query_string):
    row = find_row(table, query_string)
    if row:
        for c in row:
            if c['type'] in ('integer'): 
                return int(c['value'])
            elif c['type'] in ('large_num', 'small_float'):
                return float(c['value'].replace(",", ""))



def filter_time_series(table, query_string, subtypes = ['dollar'], treshold = 0.4):
    time_index = find_column(table, "", subtypes=['date'])
    value_index = find_column(table, query_string, subtypes = subtypes)

    for r in table['data']:
        dt = get_fuzzy_date(r[time_index]['value'])
        if dt:
            c = r[value_index]
            v = None
            if c['type'] in ('integer'): 
                v = int(c['value'])
            elif c['type'] in ('large_num', 'small_float'):
                v = float(c['value'].replace(",", ""))
            if v: yield dt, v

def get_key_values(table, key_queries):
    return { k : closest_row_numeric_value(table, kk) for k, kk in key_queries.iteritems() }