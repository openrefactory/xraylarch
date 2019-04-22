#!/usr/bin/env python
"""
Linear Combination panel
"""
import os
import time
import wx
import wx.grid as wxgrid
import numpy as np
import pickle
import base64

from functools import partial
from collections import OrderedDict

from lmfit.printfuncs import gformat
from larch import Group
from larch.math import index_of
from larch.wxlib import (BitmapButton, TextCtrl, FloatCtrl, get_icon,
                         SimpleText, pack, Button, HLine, Choice, Check,
                         CEN, RCEN, LCEN, Font)
from larch.io import read_csv
from larch.utils.strutils import fix_varname

from .taskpanel import TaskPanel

# plot options:
norm   = 'Normalized \u03bC(E)'
dmude  = 'd\u03bC(E)/dE'
chik   = '\u03c7(k)'
noplot = '<no plot>'
noname = '<none>'

CSV_WILDCARDS = "CSV Files(*.csv,*.dat)|*.csv*;*.dat|All files (*.*)|*.*"
MODEL_WILDCARDS = "Regression Model Files(*.regmod,*.dat)|*.regmod*;*.dat|All files (*.*)|*.*"

FitSpace_Choices = [norm, dmude, chik]
Plot_Choices = ['Mean Spectrum + Active Energies',
                'Spectra Stack',
                'Predicted External Varliable']

Regress_Choices = ['Partial Least Squares', 'LassoLars', 'Lasso']

defaults = dict(fitspace=norm, fit_intercept=True, alpha=0.01,
                varname='valence', xmin=-5.e5, xmax=5.e5)

NROWS = 5000

def make_steps(max=1, decades=8):
    steps = [1.0]
    for i in range(6):
        steps.extend([(j*10**(-(1+i))) for j in (5, 2, 1)])
    return steps

class NumericCombo(wx.ComboBox):
    """
    Numeric Combo: ComboBox with numeric-only choices
    """
    def __init__(self, parent, choices, default=None, width=100):
        self.choices  = choices
        schoices = ["%.6g"%(x) for x in choices]
        wx.ComboBox.__init__(self, parent, -1, '', (-1, -1), (width, -1),
                             schoices, wx.CB_DROPDOWN|wx.TE_PROCESS_ENTER)
        if default is None or default not in choices:
            default = choices[0]
        self.SetStringSelection("%.6g" % default)
        self.Bind(wx.EVT_TEXT_ENTER, self.OnEnter)

    def OnEnter(self, event=None):
        thisval = float(event.GetString())
        if thisval not in self.choices:
            self.choices.append(thisval)
            self.choices.sort()
        self.choices.reverse()
        self.Clear()
        self.AppendItems(["%.6g" % x for x in self.choices])
        self.SetSelection(self.choices.index(thisval))

class ExtVarDataTable(wxgrid.GridTableBase):
    def __init__(self):
        wxgrid.GridTableBase.__init__(self)
        self.colLabels = [' File /Group Name   ',
                          'External Value', 'Predicted Value']
        self.dataTypes = [wxgrid.GRID_VALUE_STRING,
                          wxgrid.GRID_VALUE_FLOAT+ ':12,4',
                          wxgrid.GRID_VALUE_FLOAT+ ':12,4']


        self.data = []
        for i in range(NROWS):
            self.data.append([' ', 0, 0])

    def GetNumberRows(self):
        return NROWS

    def GetNumberCols(self):
        return 3

    def GetValue(self, row, col):
        try:
            return self.data[row][col]
        except IndexError:
            return ''

    def SetValue(self, row, col, value):
        self.data[row][col] = value

    def GetColLabelValue(self, col):
        return self.colLabels[col]

    def GetRowLabelValue(self, row):
        return "%d" % (row+1)

    def GetTypeName(self, row, col):
        return self.dataTypes[col]

    def CanGetValueAs(self, row, col, typeName):
        colType = self.dataTypes[col].split(':')[0]
        if typeName == colType:
            return True
        else:
            return False

    def CanSetValueAs(self, row, col, typeName):
        return self.CanGetValueAs(row, col, typeName)

class ExtVarTableGrid(wxgrid.Grid):
    def __init__(self, parent):
        wxgrid.Grid.__init__(self, parent, -1)

        self.table = ExtVarDataTable()
        self.SetTable(self.table, True)
        self.SetRowLabelSize(30)
        self.SetMargins(10, 10)
        self.EnableDragRowSize()
        self.EnableDragColSize()
        self.AutoSizeColumns(False)
        self.SetColSize(0, 225)
        self.SetColSize(1, 125)
        self.SetColSize(2, 125)

        self.Bind(wxgrid.EVT_GRID_CELL_LEFT_DCLICK, self.OnLeftDClick)

    def OnLeftDClick(self, evt):
        if self.CanEnableCellControl():
            self.EnableCellEditControl()

class RegressionPanel(TaskPanel):
    """Regression Panel"""
    def __init__(self, parent, controller, **kws):
        TaskPanel.__init__(self, parent, controller,
                           configname='lasso_config', config=defaults,
                           title='Regression and Feature Selection', **kws)
        self.result = None
        self.save_csvfile   = 'RegressionData.csv'
        self.save_modelfile = 'Model.regmod'

    def process(self, dgroup, **kws):
        """ handle processing"""
        if self.skip_process:
            return
        self.skip_process = True
        form = self.read_form()

    def build_display(self):
        panel = self.panel
        wids = self.wids
        self.skip_process = True

        wids['fitspace'] = Choice(panel, choices=FitSpace_Choices, size=(250, -1))
        wids['fitspace'].SetStringSelection(norm)
        # wids['plotchoice'] = Choice(panel, choices=Plot_Choices,
        #                           size=(250, -1), action=self.onPlot)

        wids['method'] = Choice(panel, choices=Regress_Choices, size=(250, -1))

        add_text = self.add_text

        opts = dict(digits=2, increment=1.0)

        w_xmin = self.add_floatspin('xmin', value=defaults['xmin'], **opts)
        w_xmax = self.add_floatspin('xmax', value=defaults['xmax'], **opts)
        wids['alpha'] =  NumericCombo(panel, make_steps(), default=0.01, width=100)

        wids['auto_alpha'] = Check(panel, default=False, label='auto?')

        # wids['fit_intercept'] = Check(panel, default=True, label='fit intercept?')

        wids['save_csv'] = Button(panel, 'Save CSV File', size=(125, -1),
                                    action=self.onSaveCSV)
        wids['load_csv'] = Button(panel, 'Load CSV File', size=(125, -1),
                                    action=self.onLoadCSV)

        wids['save_model'] = Button(panel, 'Save Model', size=(125, -1),
                                    action=self.onSaveModel)
        wids['save_model'].Disable()

        wids['load_model'] = Button(panel, 'Load Model', size=(125, -1),
                                    action=self.onLoadModel)


        wids['train_model'] = Button(panel, 'Train Model From These Data',
                                     size=(275, -1),  action=self.onTrainModel)

        wids['fit_group'] = Button(panel, 'Predict Variable for Selected Groups',
                                   size=(275, -1), action=self.onPredictGroups)
        wids['fit_group'].Disable()


        w_cvfolds = self.add_floatspin('cv_folds', digits=0, with_pin=False,
                                       value=0, increment=1, min_val=-1)

        w_cvreps  = self.add_floatspin('cv_repeats', digits=0, with_pin=False,
                                       value=0, increment=1, min_val=-1)

        wids['varname'] = wx.TextCtrl(panel, -1, 'valence', size=(150, -1))
        wids['stats'] =  SimpleText(panel, ' ')

        wids['table'] = ExtVarTableGrid(panel)
        wids['table'].SetMinSize((550, 200))

        wids['use_selected'] = Button(panel, 'Use Selected Groups',
                                     size=(175, -1),  action=self.onFillTable)

        panel.Add(SimpleText(panel, 'Feature Regression, Model Selection',
                             font=Font(12), colour='#AA0000'), dcol=4)
        add_text('Array to Use: ', newrow=True)
        panel.Add(wids['fitspace'], dcol=3)

        # add_text('Plot : ', newrow=True)
        # panel.Add(wids['plotchoice'], dcol=3)

        add_text('Fit Energy Range: ')
        panel.Add(w_xmin)
        add_text(' : ', newrow=False)
        panel.Add(w_xmax)
        add_text('Regression Method:')
        panel.Add(wids['method'], dcol=3)
        add_text('Lasso Alpha: ')
        panel.Add(wids['alpha'])
        panel.Add(wids['auto_alpha'], dcol=2)

        add_text('Cross Validation: ')
        add_text(' # folds: ', newrow=False)
        panel.Add(w_cvfolds)
        add_text(' # repeats: ', newrow=False)
        panel.Add(w_cvreps)

        panel.Add(HLine(panel, size=(550, 2)), dcol=5, newrow=True)

        add_text('External Variable for each Data Set: ', newrow=True, dcol=2)
        panel.Add(wids['use_selected'],   dcol=4)
        add_text('Attribute Name: ')
        panel.Add(wids['varname'], dcol=4)

        panel.Add(wids['table'], newrow=True, dcol=4, drow=3)

        icol = panel.icol
        irow = panel.irow
        pstyle, ppad = panel.itemstyle, panel.pad

        panel.sizer.Add(wids['load_csv'], (irow,   icol), (1, 1), pstyle, ppad)
        panel.sizer.Add(wids['save_csv'], (irow+1, icol), (1, 1), pstyle, ppad)

        panel.irow += 2

        panel.Add(HLine(panel, size=(550, 2)), dcol=5, newrow=True)
        panel.Add((5, 5), newrow=True)
        add_text('Train Model : ')
        panel.Add(wids['train_model'], dcol=3)
        panel.Add(wids['load_model'])

        add_text('Use This Model : ')
        panel.Add(wids['fit_group'], dcol=3)
        panel.Add(wids['save_model'])
        add_text('Statistics : ')
        panel.Add(wids['stats'], dcol=4)
        panel.pack()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add((10, 10), 0, LCEN, 3)
        sizer.Add(panel, 1, LCEN, 3)
        pack(self, sizer)
        self.skip_process = False

    def fill_form(self, dgroup):
        opts = self.get_config(dgroup)
        self.dgroup = dgroup
        if isinstance(dgroup, Group):
            d_emin = min(dgroup.energy)
            d_emax = max(dgroup.energy)
            if opts['xmin'] < d_emin:
                opts['xmin'] = -40 + int(dgroup.e0/10.0)*10
            if opts['xmax'] > d_emax:
                opts['xmax'] =  110 + int(dgroup.e0/10.0)*10

        self.skip_process = True
        wids = self.wids
        for attr in ('xmin', 'xmax', 'alpha'):
            val = opts.get(attr, None)
            if val is not None:
                if attr == 'alpha':
                    val = "%.6g" % val
                wids[attr].SetValue(val)

        for attr in ('fitspace',):
            if attr in opts:
                wids[attr].SetStringSelection(opts[attr])

        self.skip_process = False

    def onFillTable(self, event=None):
        selected_groups = self.controller.filelist.GetCheckedStrings()
        varname = fix_varname(self.wids['varname'].GetValue())
        predname = varname + '_predicted'
        grid_data = []
        for fname in self.controller.filelist.GetCheckedStrings():
            gname = self.controller.file_groups[fname]
            grp = self.controller.get_group(gname)
            grid_data.append([fname, getattr(grp, varname, 0.0),
                              getattr(grp, predname, 0.0)])

        self.wids['table'].table.data = grid_data
        self.wids['table'].table.View.Refresh()

    def onTrainModel(self, event=None):
        opts = self.read_form()
        varname = opts['varname']
        predname = varname + '_predicted'

        grid_data = self.wids['table'].table.data
        groups = []
        for fname, yval, pval in grid_data:
            gname = self.controller.file_groups[fname]
            grp = self.controller.get_group(gname)
            setattr(grp, varname, yval)
            setattr(grp, predname, pval)
            groups.append(gname)

        cmds = ['# train linear regression model',
               'training_groups = [%s]' % ', '.join(groups)]

        copts = ["varname='%s'" % varname,
                 "xmin=%.4f" % opts['xmin'],
                 "xmax=%.4f" % opts['xmax'],
                 ]

        arrname = 'norm'
        if opts['fitspace'] == dmude:
            arrname = 'dmude'
        elif opts['fitspace'] == chik:
            arrname = 'chi'
        copts.append("arrayname='%s'" % arrname)

        self.method = 'pls'
        if opts['method'].lower().startswith('lasso'):
            self.method = 'lasso'
            if opts['auto_alpha']:
                copts.append('alpha=None')
            else:
                copts.append('alpha=%s' % opts['alpha'])
            if 'lars' in opts['method'].lower():
                copts.append('use_lars=True')
            else:
                copts.append('use_lars=False')
            copts.append('fit_intercept=True')
        else:
            copts.append('scale=True')

        copts = ', '.join(copts)
        cmds.append("reg_model = %s_train(training_groups, %s)" %
                    (self.method, copts))
        self.larch_eval('\n'.join(cmds))
        reg_model = self.larch_get('reg_model')
        if reg_model is not None:
            self.write_message('Regression Model trained: %s' % opts['method'])
            rmse_cv = reg_model.rmse_cv
            if rmse_cv is not None:
                rmse_cv = "%.4f" % rmse_cv
            stat = ["RMSE_CV = %s, RMSE = %.4f" % (rmse_cv, reg_model.rmse), '']
            if self.method == 'lasso':
                stat[1] = "Alpha = %.4f, %d active components"
                stat[1]= stat[1] % (reg_model.alpha, len(reg_model.active))
            self.wids['stats'].SetLabel(", ".join(stat))

            for i, row in enumerate(grid_data):
                grid_data[i] = [row[0], row[1], reg_model.ypred[i]]
            self.wids['table'].table.data = grid_data
            self.wids['table'].table.View.Refresh()

            self.onPlotModel(model=reg_model)
            self.wids['save_model'].Enable()
            self.wids['fit_group'].Enable()

    def onPredictGroups(self, event=None):
        opts = self.read_form()
        varname = opts['varname'] + '_predicted'

        grid_data = self.wids['table'].table.data
        gent = {}
        if len(grid_data[0][0].strip()) == 0:
            grid_data = []
        else:
            for i, row in enumerate(grid_data):
                gent[row[0]] = i

        for fname in self.controller.filelist.GetCheckedStrings():
            gname = self.controller.file_groups[fname]
            cmd = "%s.%s = %s_predict(%s, lasso_model)" % (gname, varname,
                                                           self.method, gname)
            self.larch_eval(cmd)
            val = self.larch_get('%s.%s' % (gname, varname))
            if fname in gent:
                grid_data[gent[fname]][2] = val
            else:
                grid_data.append([fname, 0, val])
            self.wids['table'].table.data = grid_data
            self.wids['table'].table.View.Refresh()

    def onSaveModel(self, event=None):
        try:
            reg_model = self.larch_get('reg_model')
        except:
            reg_model = None
        if reg_model is None:
            self.write_message('Cannot Save Regression Model')
            return

        dlg = wx.FileDialog(self, message="Save Regression Model",
                            defaultDir=os.getcwd(),
                            defaultFile=self.save_modelfile,
                            wildcard=MODEL_WILDCARDS,
                            style=wx.FD_SAVE)
        fname = None
        if dlg.ShowModal() == wx.ID_OK:
            fname = dlg.GetPath()
        dlg.Destroy()
        if fname is None:
            return
        self.save_modelfile = os.path.split(fname)[1]
        text = str(base64.b64encode(pickle.dumps(reg_model)), 'utf-8')
        with open(fname, 'w') as fh:
            fh.write("%s\n" % text)
        fh.flush()
        fh.close()
        self.write_message('Wrote Regression Model to %s ' % fname)

    def onLoadModel(self, event=None):
        dlg = wx.FileDialog(self, message="Load Regression Model",
                            defaultDir=os.getcwd(),
                            wildcard=MODEL_WILDCARDS, style=wx.FD_OPEN)

        fname = None
        if dlg.ShowModal() == wx.ID_OK:
            fname = dlg.GetPath()
        dlg.Destroy()
        if fname is None:
            return
        self.save_modelfile = os.path.split(fname)[1]
        with open(fname, 'r') as fh:
            text = fh.read()

        reg_model = pickle.loads(base64.b64decode(bytes(text, 'utf-8')))
        self.controller.symtable.reg_model = reg_model
        self.write_message('Read Regression Model from %s ' % fname)
        self.wids['fit_group'].Enable()


    def onLoadCSV(self, event=None):
        dlg = wx.FileDialog(self, message="Load CSV Data File",
                            defaultDir=os.getcwd(),
                            wildcard=CSV_WILDCARDS, style=wx.FD_OPEN)

        fname = None
        if dlg.ShowModal() == wx.ID_OK:
            fname = dlg.GetPath()
        dlg.Destroy()
        if fname is None:
            return

        self.save_csvfile = os.path.split(fname)[1]
        varname = fix_varname(self.wids['varname'].GetValue())
        csvgroup = read_csv(fname)
        script = []
        grid_data = []
        for sname, yval in zip(csvgroup.col_01, csvgroup.col_02):
            if sname.startswith('#'):
                continue
            if sname in self.controller.file_groups:
                gname = self.controller.file_groups[sname]
                script.append('%s.%s = %f' % (gname, varname, yval))
                grid_data.append([sname, yval, 0])

        self.larch_eval('\n'.join(script))
        self.wids['table'].table.data = grid_data
        self.wids['table'].table.View.Refresh()
        self.write_message('Read CSV File %s ' % fname)

    def onSaveCSV(self, event=None):
        dlg = wx.FileDialog(self, message="Save CSV Data File",
                            defaultDir=os.getcwd(),
                            defaultFile=self.save_csvfile,
                            wildcard=FILE_WILDCARDS,
                            style=wx.FD_SAVE)
        fname = None
        if dlg.ShowModal() == wx.ID_OK:
            fname = dlg.GetPath()
        dlg.Destroy()
        if fname is None:
            return
        self.save_csvfile = os.path.split(fname)[1]

        buff = []
        for  row in self.wids['table'].table.data:
            buff.append("%s, %s, %s" % (row[0], gformat(row[1]), gformat(row[2])))
        buff.append('')
        with open(fname, 'w') as fh:
            fh.write('\n'.join(buff))
        self.write_message('Wrote CSV File %s ' % fname)

    def onPlotModel(self, event=None, model=None):
        opts = self.read_form()
        if model is None:
            return

        ppanel = self.controller.get_display(win=1).panel
        viewlims = ppanel.get_viewlimits()
        plotcmd = ppanel.plot

        d_ave = model.spectra.mean(axis=0)
        d_std = model.spectra.std(axis=0)
        ymin, ymax = (d_ave-d_std).min(), (d_ave+d_std).max()
        if self.method == 'lasso':
            active_coefs = (model.coefs[model.active])
            active_coefs = active_coefs/max(abs(active_coefs))
            ymin = min(active_coefs.min(), ymin)
            ymax = max(active_coefs.max(), ymax)

        else:
            ymin = min(model.coefs.min(), ymin)
            ymax = max(model.coefs.max(), ymax)

        ymin = ymin - 0.02*(ymax-ymin)
        ymax = ymax + 0.02*(ymax-ymin)

        ppanel.plot(model.x, d_ave, win=1,
                    label='mean spectra', xlabel='Energy (eV)',
                    ylabel=opts['fitspace'], show_legend=True,
                    ymin=ymin, ymax=ymax)
        ppanel.axes.fill_between(model.x, d_ave-d_std, d_ave+d_std,
                                 color='#d6272844')
        if self.method == 'lasso':
            ppanel.axes.bar(model.x[model.active], active_coefs,
                            1.5, color='#9f9f9f88',
                            label='coefficients')
        else:
            ppanel.oplot(model.x, model.coefs, linewidth=0,
                         marker='o', color='#9f9f9f88',
                         label='coefficients')

        ppanel.canvas.draw()

        ngoups = len(model.groupnames)
        indices = np.arange(len(model.groupnames))
        diff = model.ydat - model.ypred
        sx = np.argsort(model.ydat)

        ppanel = self.controller.get_display(win=2).panel

        ppanel.plot(model.ydat[sx], indices, xlabel='valence',
                    label='experimental', linewidth=0, marker='o',
                    markersize=8, win=2, new=True)

        ppanel.oplot(model.ypred[sx], indices, label='predicted',
                    labelfontsize=7, markersize=6, marker='o',
                    linewidth=0, show_legend=True, new=False)

        ppanel.axes.barh(indices, diff[sx], 0.5, color='#9f9f9f88')
        ppanel.axes.set_yticks(indices)
        ppanel.axes.set_yticklabels([model.groupnames[o] for o in sx])
        ppanel.conf.set_margins(left=0.3)
        ppanel.canvas.draw()


    def onCopyParam(self, name=None, evt=None):
        print("on Copy Param")
        conf = self.get_config()