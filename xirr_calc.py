
# coding: utf-8

#Calculations adapted from Marc Joffe, 2016 

import os
import sys
import json
from backend import *
from data_query import *

import traceback
import time

from itertools import chain

def calc_net_proceeds(table, first_cf_dict, log=None):
    v = get_key_values(table, first_cf_dict)
    if log:
        log.append("working with these values for calculating net proceeds: %s" % str(v))
        if not (v['premium'] or v['discount'] or v['underwriter_discount']):
            log.append("<b>Warning: </b> neither premium nor discount found")
    
    net_proceeds_calc = + v['face_value'] \
                        + (v['premium'] or 0.) \
                        - (v['discount'] or 0.) \
                        - v['underwriter_discount'] \
                        - v['cost_of_issuance']   

    # Added by Marc 20160306 - Calculate and display cost of issuance and underwriter discount data
    total_cost_of_issuance = v['underwriter_discount'] + v['cost_of_issuance']
    total_cost_of_issuance_pct_of_face = total_cost_of_issuance / v['face_value']
    underwriter_discount_pct_of_face = v['underwriter_discount'] / v['face_value']
    log.append("Underwriter Discount as Percent of Face Value: <b>%s</b>" % '{:5.4f}'.format(underwriter_discount_pct_of_face))
    log.append("Total Cost of Issuance as Percent of Face Value: <b>%s</b>" % '{:5.4f}'.format(total_cost_of_issuance_pct_of_face))
    log.append("Total Cost of Issuance (Including Underwiter Discount): <b>%s</b>" % '{:15,.2f}'.format(total_cost_of_issuance))

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
        log.append("Try fetching due date with first occurrence of fuzzy term: <i>%s</i>" % due_date_query)
        due_date, date_linenr, line_str = get_first_date(file_lines, 'deliver') 

        log.append("... succeeded with date <b>%s</b> in line %i" % (str(due_date), date_linenr))

        # Get first cash flow
        first_cf_dict = {'face_value' : ['Principal Amount', 'Par Amount', 'Face Amount'], 
                         'premium' : 'Issue Premium',
                         'discount': 'Issue Discount',
                        'underwriter_discount' : 'Underwriter Discount', 'cost_of_issuance' : 'Costs of Issuance'}

        log.append("Try calculating first cashflow by fetching with those fuzzy terms: <i>%s</i>" % str(first_cf_dict.values()))
        net_proceeds = calc_net_proceeds(funds_table, first_cf_dict, log)
        log.append("... succeed with first cashflow as net proceeds of <b>%s</b>" % '{:,.2f}'.format(net_proceeds))

        # Get the rest of the time series
        payments_column = "Debt Service"
        log.append("Getting remaining time series by looking for first date column and a column of subtype 'dollar' named similar to <i>'%s'</i>" % payments_column)
        cf_time = chain( ((due_date, net_proceeds),) , 
                            ((d, -v) for d,v in filter_time_series(schedule_table, payments_column)))
        dates = {}
        payments = []
        # Convert our sequence of dates and cashflows into random access iterables
        for i, cf_dt in enumerate(cf_time):
            date, cf = cf_dt[0], cf_dt[1]
            dates[i]=date
            payments.append(cf)
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
        log.append('<span style="text-decoration:underline">Cashflow and Dates</span>')
        #log.append("-------------------------")
        for i, dte in enumerate(dates.values()):
            log.append ("<pre>%i | %s ... $ %s</pre>" % (i, str(dte), '{:,.2f}'.format(payments[i])) )

    log.append('<span style="text-decoration:underline">Guesses Summary</span>')
    
    for i, g in enumerate(calculator.guesses):
        log.append("%i guessed %0.10f" % (i +1,  g))

    log.append("Calculation time: %s seconds" % elapsed_time)
    return final_rate, log

