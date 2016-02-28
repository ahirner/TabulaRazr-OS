from datetime import date
import dateutil.parser as date_parser

from backend import config
from fuzzywuzzy import fuzz


# Cascades:
# 1) case sensitive partial ratio on character level with penalty
# 2) case insensitive partial ratio on character level with penalty
# 3) token sorted case insensitive ratio with penalty
FUZZY_INV_CASCADES = 1.0 / 3.0
def fuzzy_str_match(query, string):

    score = 1.0
    inv_cascades = FUZZY_INV_CASCADES
    min_fuzzy_ratio = config["min_fuzzy_ratio"]

    query = query.encode('ascii', errors='ignore')    
    string = string.encode('ascii', errors='ignore')
    
    #Penalize shorter target strings and early exit on null length strings
    len_query = len(query)
    len_string = len(string.strip())
    if not len_string: return None
    if not len_query: return score
    penalty = min(len_string / float(len_query), 1.0)
    
    fuzzy_partial = (fuzz.partial_ratio(query, string)/100.0) * penalty
    #print ("fuzzy_partial of %s vs %s * penalty %.2f" % (query, string, penalty), fuzzy_partial)
    if fuzzy_partial > min_fuzzy_ratio:
        f_score = score - (1.0 - (fuzzy_partial - (1.0 - min_fuzzy_ratio)) / min_fuzzy_ratio) * inv_cascades
        return f_score
    score -= inv_cascades

    q_l = query.lower()
    s_l = string.lower()

    fuzzy_partial = (fuzz.partial_ratio(q_l, s_l)/100.0) * penalty
    #print ("fuzzy_partial lower_case of %s vs %s * penalty %.2f" % (query, string, penalty), fuzzy_partial)
    
    if fuzzy_partial > min_fuzzy_ratio:
        f_score = score - (1.0 - (fuzzy_partial - (1.0 - min_fuzzy_ratio)) / min_fuzzy_ratio) * inv_cascades
        return f_score
    score -= inv_cascades

    fuzzy_partial = (fuzz.partial_token_sort_ratio(q_l, s_l)/100.0) * penalty
    #print ("fuzzy_partial token_sort_lower_case of %s vs %s * penalty %.2f" % (query, string, penalty), fuzzy_partial)    
    if fuzzy_partial > min_fuzzy_ratio:
        f_score = score - (1.0 - (fuzzy_partial - (1.0 - min_fuzzy_ratio)) / min_fuzzy_ratio) * inv_cascades
        return f_score

    return None

#Flatmap from tables to sequence of tuples (confidence, table, row or None, value or None)
def filter_tables(tables, filter_dict, treshold = 0.0, only_max = False):
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
                    scores_indices = ((val, idx) for (idx, val) in enumerate(fuzzy_str_match(term, h) for h in t['headers'] ) )

                    conf, idx = max(scores_indices)
                
                    if conf > max_conf:
                        max_conf = conf
                        index = idx
                        best_term = term
                        best_header = ""
            
            #Todo: other filter criteria like column names, rows etc. and combinatorial confidence score
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
                   
def find_row(table, query_string, threshold = 0.4):
    #Find first 'other' typed row
    try:
        index = table['types'].index('other')
    except ValueError:
        print "no column consisting of mainly string data found"
        return None
    
    strings = (s[index]['value'] for s in table['data'])
    scores_indices = ((val, idx) for (idx, val) in enumerate(fuzzy_str_match(query_string, s) for s in strings ) )
    val, idx = max(scores_indices)
    if val >= threshold:
        return table['data'][idx]
    else:
        return None


def closest_row_numeric_value(table, query_string, threshold = 0.4):
    row = find_row(table, query_string, threshold)
    if row:
        for c in row:
            if c['type'] in ('integer'): 
                return int(c['value'])
            elif c['type'] in ('large_num', 'small_float'):
                return float(c['value'].replace(",", ""))


def get_key_values(table, key_queries, threshold = 0.4):
    return { k : closest_row_numeric_value(table, kk, threshold) for k, kk in key_queries.iteritems() }


def find_column(table, query_string, types=None, subtypes=None, threshold = 0.4):
    #Find first column with specific types
    columns = []
    for i, t in enumerate(zip(table['types'], table['subtypes'])):
        t, st = t[0], t[1]
        if t in (types or t) and st in (subtypes or st):
            if fuzzy_str_match(query_string, table['captions'][i]) > threshold: return i

def filter_time_series(table, query_string, subtypes = ['dollar'], threshold = 0.4):
    time_index = find_column(table, "", subtypes=['date', 'year'], threshold=threshold)
    value_index = find_column(table, query_string, subtypes=subtypes, threshold=threshold)

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
