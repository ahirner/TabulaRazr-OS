
# coding: utf-8

#Downstream calculations adapted from Marc Joffe, 2016 

import os
import sys
import json
from backend import *

from datetime import date
import dateutil.parser as date_parser

import traceback
import time

from itertools import chain

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


# In[3]:

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

def calc_net_proceeds(table, first_cf_dict):
    v = get_key_values(table, first_cf_dict)
    net_proceeds_calc = v['face_value'] + v['premium_or_discount'] - v['underwriter_discount'] - v['cost_of_issuance']   
    return net_proceeds_calc


#Todo: refactor into class
debug_each_guess = True  # Change to True for verbose output


def newton(func, x0, fprime=None, args=(), tol=1.48e-8, maxiter=50):
    """Given a function of a single variable and a starting point,
    find a nearby zero using Newton-Raphson.

    fprime is the derivative of the function.  If not given, the
    Secant method is used.

    # Source: http://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.newton.html
    # File:   scipy.optimize.minpack.py
    # License: BSD: http://www.scipy.org/License_Compatibility
    """

    if fprime is not None:
        p0 = x0
        for iter in range(maxiter):
            myargs = (p0,)+args
            fval = func(*myargs)
            fpval = fprime(*myargs)
            if fpval == 0:
                print "Warning: zero-derivative encountered."
                return p0
            p = p0 - func(*myargs)/fprime(*myargs)
            if abs(p-p0) < tol:
                return p
            p0 = p
    else: # Secant method
        p0 = x0
        p1 = x0*(1+1e-4)
        q0 = func(*((p0,)+args))
        q1 = func(*((p1,)+args))
        for iter in range(maxiter):
            if q1 == q0:
                if p1 != p0:
                    print "Tolerance of %s reached" % (p1-p0)
                return (p1+p0)/2.0
            else:
                p = p1 - q1*(p1-p0)/(q1-q0)
            if abs(p-p1) < tol:
                return p
            p0 = p1
            q0 = q1
            p1 = p
            q1 = func(*((p1,)+args))
    raise RuntimeError, "Failed to converge after %d iterations, value is %s" % (maxiter,p)

class xirr_calc(object):
    
    def __init__(self):
        self.guess_num = 0
        self.debug_each_guess = False
        self.guesses = []

    def eir_func(self, rate, pmts, dates):
        """Loop through the dates and calculate a discounted cashflow total

        This is a simple process, but the debug messages clutter it up to
        make it seem more complex than it is.  With the debug messages removed,
        it is very similar to eir_derivative_func, but with the EIR formula,
        rather than f'rate.

        Credit: http://mail.scipy.org/pipermail/numpy-discussion/2009-May/042736.html
        """

        # Globals used for debug printing

        print_debug_messages = self.debug_each_guess
        if rate not in self.guesses:
            self.guesses.append(rate)
            if print_debug_messages:
                print "-----------------------------------------------------------------------------------------------"
                print "Guess #%s:  %s" % (self.guess_num, rate)
                print ""
                print "   # DATE          # DAYS  CASHFLOW      DISCOUNTED    Formula: cf * (rate + 1)^(-days/365)"
                print "   --------------------------------------------------------------------------------------------"
            self.guess_num +=1

        dcf=[]
        for i, cf in enumerate(pmts):
            d = dates[i] - dates[0]
            discounted_period = cf * (rate + 1)**(-d.days / 365.)
            dcf.append( discounted_period )

            if print_debug_messages:
                cf = "%.2f" % cf
                cf = cf.rjust(9, " ")
                discounted_period = '%.8f' % discounted_period
                formula = '%s * ((%0.10f + 1)^(-%d /365)) ' % (cf, rate, d.days)
                discounted_period = discounted_period.rjust(15, " ")
                print "  %2i %s  %3.0d days %s %s =%s"  %                 (i, dates[i], d.days, cf, discounted_period, formula )

        discounted_cashflow = sum(dcf)

        if print_debug_messages:
            discounted_cashflow = "%.8f" % discounted_cashflow
            total = "total:".rjust(35, " ")
            print "%s %s" % (total, discounted_cashflow.rjust(15, " "))
            print ""

        return discounted_cashflow

def eir_derivative_func(rate, pmts, dates):
    """Find the derivative or the EIR function, used for calculating
    Newton's method:

    http://en.wikipedia.org/wiki/Newton's_method

    EIR = cf*(1+rate)^d
    f'rate = cf*d*(rate+1)^(d-1)

    Credit: http://mail.scipy.org/pipermail/numpy-discussion/2009-May/042736.html
    """

    dcf=[]
    for i, cf in enumerate(pmts):
        d = dates[i] - dates[0]
        n = (-d.days / 365.)
        dcf.append( cf * n * (rate + 1)**(n - 1) )
    return sum(dcf)

def xirr(file_lines, funds_table, schedule_table):
    
    try:
        log = []

        # Get due date
        due_date_query = 'deliver'
        log.append("Trying to fetch first date with fuzzy term <i>%s</i>" % due_date_query)
        try: 
            due_date, date_linenr, line_str = get_first_date(file_lines, 'deliver') 
        except Exception as e:
            log.append("... failed with %s" % traceback.format_exception(*sys.exc_info()))
            raise

        log.append("... succeeded with date <b>%s</b> in line %i" % (str(due_date), date_linenr))

        # Get first cash flow
        first_cf_dict = {'face_value' : 'Principal Amount', 'premium_or_discount' : 'Issue Premium',
                        'underwriter_discount' : 'Underwriter Discount', 'cost_of_issuance' : 'Costs of Issuance'}

        log.append("Trying to calculate first cashflow by fetching with those fuzzy terms <i>%s</i>" % str(first_cf_dict.values()))
        try:
            net_proceeds = calc_net_proceeds(funds_table, first_cf_dict)
        except Exception as e:
            log.append("... failed with %s" % traceback.format_exception(*sys.exc_info()))
            raise
        log.append("... succeed with first cashflow as net proceeds of <b>%f</b>" % net_proceeds)

        # Get the rest of the time series
        payments_column = "Debt Service"
        log.append("Getting remaining time series by looking for the first date column and a column of subtype 'dollar' named similar to <i>'%s'</i>" % payments_column)
        try:
            cf_time = chain( ((due_date, net_proceeds),) , 
                            ((d, -v) for d,v in filter_time_series(schedule_table, payments_column)))
        except Exception as e:
            log.append("... failed with %s" % traceback.format_exception(*sys.exc_info()))
            raise

        dates = {}
        payments = []
        # Convert our sequence of dates and cashflows into random access iterables
        for i, cf_dt in enumerate(cf_time):
            date, cf = cf_dt[0], cf_dt[1]
            dates[i]=date
            payments.append(cf)
        print "HEELLO"
        log.append("... succeed and yielded <b>%i</b> date / cashflow tuples" % len(payments))
 
    except Exception as e:
        log.append("... failed with %s" % traceback.format_exception(*sys.exc_info()))
        return None, log
    
    # Begin Main Calculation
    guess = .05
    calculator = xirr_calc()
    
    maxiter=100
    timer_start = time.clock()
    if len(dates) > 1:
        f = lambda x: calculator.eir_func(x, payments, dates)
        derivative = lambda x: eir_derivative_func(x, payments, dates)
        try:
            rate = newton(f, guess, fprime=derivative, args=(),
                tol=0.00000000001, maxiter=maxiter)
        except RuntimeError:
            log.append("failed to converge after a maxiumum of %i iterations" %maxiter)

    timer_end = time.clock()
    # End Main Calculation

    elapsed_time = timer_end - timer_start
    final_rate = rate * 100

    if not calculator.debug_each_guess:
        log.append("")
        log.append("Cashflow and Dates: ")
        log.append("-------------------------")
        for i, dte in enumerate(dates.values()):
            log.append ("<pre>%i | %s ... $ %s</pre>" % (i, str(dte), str(payments[i])))

    log.append("Guesses Summary")
    log.append("------------------")

    for i, g in enumerate(calculator.guesses):
        log.append("%i guessed %0.10f" % (i +1,  g))

    log.append("Calculation time: %s seconds" % elapsed_time)
    return final_rate, log

