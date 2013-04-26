"""
setup.py script for cx_Freeze

Usage:
    python setup_freeze.py bdist_mac --bundle-iconfile=cameras.icns
    cp cameras.icns build/GSE.../Contents/Resources/.
    cp dlls/*.dylib builf/GSE.../Contents/MacOS/.
"""

from cx_Freeze import setup, Executable

import os, sys
import wx
import wx.lib.agw.flatnotebook
import numpy, scipy, matplotlib
matplotlib.use('WXAgg')
import sqlalchemy

from scipy.sparse.csgraph import _validation
from  scipy.io import netcdf
netcdf_open = netcdf.netcdf_file

import wxmplot
from wxmplot.plotframe import PlotFrame
import larch

import Image
import epics
import Carbon

libca = epics.ca.initialize_libca()
mpl_data_files = matplotlib.get_py2exe_datafiles()

resource_files = ['../COPYING']
## also: use
##  if getattr(sys, 'frozen', None) == 'macosx_app':
## in lib/site_config.py to specify plugin path

plugin_files = []
psrc = "/usr/share/larch"
for dname in os.listdir('%s/plugins' % psrc):
    pname = '%s/plugins/%s' % (psrc, dname)
    if os.path.isdir(pname):
        flist = ['%s/%s' % (pname, f) for f in os.listdir(pname) if not f.endswith('.pyc')]
        plugin_files.append(("larch/plugins/%s" % dname, flist))


dll_files = [("larch/dlls/darwin/",
              ['%s/dlls/darwin/%s' % (psrc, f) for f in os.listdir('%s/dlls/darwin' % psrc)]
              )]

DATA_FILES = []

exe_opts = {# 'packages': ['wx', 'numpy','sqlalchemy'],
            'includes': ['Image', 'ctypes',
                         'sqlalchemy', 'sqlalchemy.orm', 'sqlalchemy.pool',
                         'sqlite3', 'sqlalchemy.dialects.sqlite',
                         'numpy', 'scipy', 'scipy.optimize',
                         'scipy.signal', 'scipy.constants', 'scipy.fftpack',
                         'scipy.sparse.csgraph._validation',
                         'scipy.io.netcdf',
                         'scipy.io.matlab.mio5_utils',
                         'scipy.io.matlab.streams',
                         'wx', 'wx._core', 'wx.py', 'wxversion',
                         'wx.lib', 'wx.lib.masked', 'wx.lib.mixins',
                         'wx.lib.mixins.inspection',
                         'wx.lib.colourselect', 'wx.lib.newevent',
                         'wx.lib.agw', 'wx.lib.agw.flatnotebook',
                         'h5py', 'h5py._objects', 'h5py.defs', 'h5py.utils', 'h5py._proxy',
                         'matplotlib', 'wxmplot', 'ConfigParser', 'fpformat',
                         'xml.etree', 'xml.etree.cElementTree', 'xdrlib',
                         'epics', 'epics.devices', 'Carbon.Appearance'],
            'excludes': ['Tkinter', '_tkinter', 'Tkconstants', 'tcl',
                         '_imagingtk', 'PIL._imagingtk', 'ImageTk',
                         'PIL.ImageTk', 'FixTk''_gtkagg', '_tkagg',
                         'matplotlib.tests',
                         'qt', 'PyQt4Gui', 'email', 'IPython'],
            # 'iconfile': 'GSEMap.icns',
            }

appname = 'GSEMapViewer'
appvers = '1.0'
setup(name = appname,
      version = appvers,
      description = "GSECARS XRM MapViewer",
      options = {'build_exe': exe_opts},
      data_files = mpl_data_files + dll_files, ##  + plugin_files
      executables = [Executable('../bin/GSE_MapViewer', base=None)])

contents = 'build/%s-%s.app/Contents' % (appname, appvers)
contents = contents.replace(' ', '\ ')

def sys(cmd):
    print ' >> ', cmd
    os.system(cmd)

sys("cp -pr  GSEMap.icns    %s/Resources/." % contents)
sys("cp -pr ../dlls/darwin/* %s/MacOS/." % contents)

try:
    os.makedirs("%s/Resources/larch/" % contents)
except:
    pass

for subdir in ('modules', 'plugins', 'dlls'):
    sys("cp -pr ../%s   %s/Resources/larch/." % (subdir, contents))

