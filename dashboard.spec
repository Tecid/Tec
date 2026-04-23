# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for HedgedLockBot.exe
Bundles Flask server + React frontend + Trading bot into a single executable.
"""

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# Get the project root
project_root = os.path.dirname(os.path.abspath(SPEC))

# React dist folder path
react_dist = os.path.join(project_root, 'client', 'dist')

# Collect all dns submodules (required by eventlet)
dns_datas, dns_binaries, dns_hiddenimports = collect_all('dns')

# Collect numpy (required by MetaTrader5)
numpy_hiddenimports = collect_submodules('numpy')

a = Analysis(
    [os.path.join(project_root, 'launcher.py')],
    pathex=[
        project_root, 
        os.path.join(project_root, 'server')
    ],
    binaries=dns_binaries,
    datas=[
        # Include React build
        (react_dist, 'client/dist'),
        # Include server directory
        (os.path.join(project_root, 'server'), 'server'),
        # Include bot modules from root
        (os.path.join(project_root, 'config.py'), '.'),
        (os.path.join(project_root, 'master.py'), '.'),
        (os.path.join(project_root, 'worker.py'), '.'),
        (os.path.join(project_root, 'states.py'), '.'),
        (os.path.join(project_root, 'strategy.py'), '.'),
        (os.path.join(project_root, 'display.py'), '.'),
    ] + dns_datas,
    hiddenimports=[
        # Eventlet and async
        'eventlet',
        'eventlet.hubs.epolls',
        'eventlet.hubs.kqueue', 
        'eventlet.hubs.selects',
        'eventlet.hubs.poll',
        'eventlet.green',
        'eventlet.green.dns',
        'eventlet.support.greendns',
        'eventlet.patcher',
        
        # DNS (required by eventlet)
        'dns',
        'dns.resolver',
        'dns.rdatatype',
        'dns.rdataclass',
        'dns.name',
        'dns.exception',
        'dns.message',
        'dns.query',
        'dns.rdata',
        'dns.rdtypes',
        'dns.rdtypes.ANY',
        'dns.rdtypes.IN',
        
        # Socket.IO
        'engineio',
        'engineio.async_drivers',
        'engineio.async_drivers.eventlet',
        'socketio',
        
        # Flask ecosystem
        'flask',
        'flask_socketio',
        'flask_jwt_extended',
        'flask_cors',
        
        # Database
        'psycopg2',
        'sqlalchemy',
        'sqlalchemy.dialects.postgresql',
        
        # Auth
        'bcrypt',
        
        # Config
        'config_loader',
        'cryptography',
        'dotenv',
        
        # Bot modules
        'config',
        'master',
        'worker', 
        'states',
        'strategy',
        'display',
        'database',
        'auth',
        'api',
        'bot_manager',
        
        # MT5 and dependencies
        'MetaTrader5',
        'numpy',
        'numpy.core',
        'numpy.core.multiarray',
        'numpy.core._multiarray_umath',
        'pandas',
        
        # Multiprocessing (for bot workers)
        'multiprocessing',
        'multiprocessing.spawn',
        'multiprocessing.popen_spawn_win32',
    ] + dns_hiddenimports + numpy_hiddenimports,
    hookspath=[os.path.join(project_root, 'hooks')],
    hooksconfig={},
    runtime_hooks=[os.path.join(project_root, 'hooks', 'hook-multiprocessing.py')],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HedgedLockBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console window with logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one
)
