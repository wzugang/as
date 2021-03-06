__lic__ = '''
/**
 * AS - the open source Automotive Software on https://github.com/parai
 *
 * Copyright (C) 2015  AS <parai@foxmail.com>
 *
 * This source code is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License version 2 as published by the
 * Free Software Foundation; See <http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt>.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
 * or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
 * for more details.
 */
 '''
 
from .dcm import *
from .s19 import *


from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

import os
import glob

__all__ = ['UIFlashloader']

class AsFlashloader(QThread):
    infor = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(int)
    def __init__(self,parent=None):
        super(QThread, self).__init__(parent)
        self.steps = [ (self.enter_extend_session,True), (self.security_extds_access,True),
                  (self.enter_program_session,True),(self.security_prgs_access,True),
                  (self.download_flash_driver,True),(self.check_flash_driver,False),
                  (self.routine_erase_flash,True), (self.download_application,True),
                  (self.check_application,False), (self.launch_application,True) ]
        self.enable = []
        for s in self.steps:
            self.enable.append(s[1])
        self.dcm = dcm(0,0x732,0x731)
        self.app = None
        self.flsdrv = None
    def is_check_application_enabled(self):
        return self.enable[8]
    def is_check_flash_driver_enabled(self):
        return self.enable[5]
    def setTarget(self,app,flsdrv=None):
        self.app = app
        self.flsdrv = flsdrv

    def GetSteps(self):
        ss = []
        for s in self.steps:
            ss.append((s[0].__name__.replace('_',' '),s[1]))
        return ss
    
    def SetEnable(self,step,enable):
        for id,s in enumerate(self.steps):
            if(step == s[0].__name__.replace('_',' ')):
                self.enable[id] = enable

    def step_progress(self,v):
        self.progress.emit(v)
        
    def transmit(self,req,exp):
        ercd,res = self.dcm.transmit(req)
        if(ercd == True):
            if(len(res)>=len(exp)):
                for i in range(len(exp)):
                    if((res[i]!=exp[i]) and (exp[i]!=-1)):
                        ercd = False
                        break
            else:
                ercd = False
        if(ercd == True):
            self.txSz += len(req)
            self.infor.emit('  success')
            self.step_progress((self.txSz*100)/self.sumSz)
        else:
            self.infor.emit('  failed')
        return ercd,res
    def enter_extend_session(self):
        return self.transmit([0x10,0x03], [0x50,0x03])
    def security_extds_access(self):
        ercd,res = self.transmit([0x27,0x01], [0x67,0x01,-1,-1,-1,-1])
        if(ercd):
            seed = (res[2]<<24) + (res[3]<<16) + (res[4]<<8) +(res[5]<<0)
            key = (seed^0x78934673)
            self.infor.emit(' send key %X from seed %X'%(key,seed))
            ercd,res = self.transmit([0x27,0x02,(key>>24)&0xFF,(key>>16)&0xFF,(key>>8)&0xFF,(key>>0)&0xFF],[0x67,0x02])
        return ercd,res
    def enter_program_session(self):
        return self.transmit([0x10,0x02], [0x50,0x02])
    def security_prgs_access(self):
        ercd,res = self.transmit([0x27,0x03], [0x67,0x03,-1,-1,-1,-1])
        if(ercd):
            seed = (res[2]<<24) + (res[3]<<16) + (res[4]<<8) +(res[5]<<0)
            key = (seed^0x94586792)
            self.infor.emit(' send key %X from seed %X'%(key,seed))
            ercd,res = self.transmit([0x27,0x04,(key>>24)&0xFF,(key>>16)&0xFF,(key>>8)&0xFF,(key>>0)&0xFF],[0x67,0x04])
        return ercd,res
    def request_download(self,address,size,identifier):
        self.infor.emit(' request download')
        return self.transmit([0x34,0x00,0x44,     \
                            (address>>24)&0xFF,(address>>16)&0xFF,(address>>8)&0xFF,(address>>0)&0xFF,   \
                            (size>>24)&0xFF,(size>>16)&0xFF,(size>>8)&0xFF,(size>>0)&0xFF,  \
                            identifier],[0x74])

    def request_upload(self,address,size,identifier):
        self.infor.emit(' request upload')
        return self.transmit([0x35,0x00,0x44,     \
                            (address>>24)&0xFF,(address>>16)&0xFF,(address>>8)&0xFF,(address>>0)&0xFF,   \
                            (size>>24)&0xFF,(size>>16)&0xFF,(size>>8)&0xFF,(size>>0)&0xFF,  \
                            identifier],[0x75])
    
    def request_transfer_exit(self):
        self.infor.emit(' request transfer exit')
        return self.transmit([0x37],[0x77])
    
    def download_one_section(self,address,size,data,identifier):
        FLASH_WRITE_SIZE = 512
        blockSequenceCounter = 1
        left_size = size
        pos = 0
        ability = int(((4096-4)/FLASH_WRITE_SIZE)) * FLASH_WRITE_SIZE
        # round up
        size2 = int((left_size+FLASH_WRITE_SIZE-1)/FLASH_WRITE_SIZE)*FLASH_WRITE_SIZE
        ercd,res = self.request_download(address,size2,identifier)
        if(ercd == False):return ercd,res
        while(left_size>0 and ercd==True):
            req = [0x36,blockSequenceCounter,0,identifier]
            if(left_size > ability):
                sz = ability
                left_size = left_size - ability
            else:
                sz = int((left_size+FLASH_WRITE_SIZE-1)/FLASH_WRITE_SIZE)*FLASH_WRITE_SIZE
                left_size = 0
            for i in range(sz):
                if((pos+i)<size):
                    req.append(data[pos+i])
                else:
                    req.append(0xFF)
            self.infor.emit(' transfer block %s'%(blockSequenceCounter))
            ercd,res = self.transmit(req,[0x76,blockSequenceCounter])
            if(ercd == False):return ercd,res
            blockSequenceCounter = (blockSequenceCounter + 1)&0xFF
            pos += sz
        ercd,res = self.request_transfer_exit()
        if(ercd == False):return ercd,res
        return ercd,res

    def upload_one_section(self,address,size,identifier):
        FLASH_READ_SIZE = 512
        blockSequenceCounter = 1
        left_size = size
        ability = int(((4096-4)/FLASH_READ_SIZE)) * FLASH_READ_SIZE
        # round up
        size2 = int((left_size+FLASH_READ_SIZE-1)/FLASH_READ_SIZE)*FLASH_READ_SIZE
        ercd,res = self.request_upload(address,size2,identifier)
        if(ercd == False):return ercd,res,None
        data = []
        while(left_size>0 and ercd==True):
            req = [0x36,blockSequenceCounter,0,identifier]
            self.infor.emit(' transfer block %s'%(blockSequenceCounter))
            ercd,res = self.transmit(req,[0x76,blockSequenceCounter])
            if(ercd == False):return ercd,res,None
            blockSequenceCounter = (blockSequenceCounter + 1)&0xFF
            sz = len(res)-2
            if (left_size > sz):
                left_size = left_size - sz
            else:
                left_size = 0
            for b in res[2:]:
                data.append(b)
        ercd,res = self.request_transfer_exit()
        if(ercd == False):return ercd,res,None
        return ercd,res,data
    
    def compare(self,d1,d2):
        for i,b in enumerate(d1):
            if(b!=d2[i]):
                return False
        return True

    def download_flash_driver(self):
        flsdrv = self.flsdrvs
        ary = flsdrv.getData()
        for ss in ary:
            ercd,res = self.download_one_section(ss['address']-ary[0]['address'],ss['size'],ss['data'],0xFD)
            if(ercd == False):return ercd,res
        return ercd,res

    def check_flash_driver(self):
        flsdrv = self.flsdrvs
        ary = flsdrv.getData()
        flsdrvr = s19()
        for ss in ary:
            ercd,res,up = self.upload_one_section(ss['address']-ary[0]['address'],ss['size'],0xFD)
            flsdrvr.append(ss['address'],up)
            if(ercd and self.compare(ss['data'], up)):
                self.infor.emit('  check flash driver pass!')
            else:
                self.infor.emit('  check flash driver failed!')
                flsdrvr.dump('read_%s'%(os.path.basename(self.flsdrv)))
                return False,res
        flsdrvr.dump('read_%s'%(os.path.basename(self.flsdrv)))
        return ercd,res
    
    def routine_erase_flash(self):
        app = self.apps
        ary = app.getData(True)
        saddr = ary[0]['address']
        eaddr = ary[0]['address'] + ary[0]['size']
        for ss in ary:
            if(ss['address']< saddr):
                saddr = ss['address']
            if(ss['address']+ss['size'] > eaddr):
                eaddr = ss['address']+ss['size']
        eaddr = int((eaddr+511)/512)*512
        return self.transmit([0x31,0x01,0xFF,0x01,
                              (saddr>>24)&0xFF,(saddr>>16)&0xFF,(saddr>>8)&0xFF,(saddr>>0)&0xFF,
                              (eaddr>>24)&0xFF,(eaddr>>16)&0xFF,(eaddr>>8)&0xFF,(eaddr>>0)&0xFF,
                              0xFF],[0x71,0x01,0xFF,0x01])
    
    def download_application(self):
        app = self.apps
        ary = app.getData(True)
        for ss in ary:
            ercd,res = self.download_one_section(ss['address'],ss['size'],ss['data'],0xFF)
            if(ercd == False):return ercd,res
        return ercd,res

    def check_application(self):
        app = self.apps
        ary = app.getData(True)
        appr = s19()
        for ss in ary:
            ercd,res,up = self.upload_one_section(ss['address'],ss['size'],0xFF)
            appr.append(ss['address'],up)
            if(ercd and self.compare(ss['data'], up)):
                self.infor.emit('  check application pass!')
            else:
                self.infor.emit('  check application failed!')
                appr.dump('read_%s'%(os.path.basename(self.app)))
                return False,res
        appr.dump('read_%s'%(os.path.basename(self.app)))
        return ercd,res

    def launch_application(self):
        return self.transmit([0x31,0x01,0xFF,0x03], [0x71,0x01,0xFF,0x03])

    def run(self):
        self.infor.emit("starting ... ")
        def ssz(ss):
            sz = 0
            for s in ss.getData(True):
                sz += s['size']
            return sz
        self.sumSz = 0
        if(os.path.exists(self.flsdrv)):
            self.flsdrvs = s19(self.flsdrv)
            self.sumSz = ssz(self.flsdrvs)
            if(self.is_check_flash_driver_enabled()):
                self.sumSz += ssz(self.flsdrvs)
        self.apps = s19(self.app)
        self.sumSz += ssz(self.apps)
        if(self.is_check_application_enabled()):
            self.sumSz += ssz(self.apps)
        self.txSz = 0
        self.infor.emit('summary transfer size is %s bytes(app %s, flsdrv %s)!'%(
                        self.sumSz,ssz(self.apps),ssz(self.flsdrvs)))
        for id,s in enumerate(self.steps):
            if(self.enable[id] == True):
                self.infor.emit('>> '+s[0].__name__.replace('_',' '))
                ercd,res = s[0]()
                if(ercd == False):
                    self.infor.emit("\n\n  >> boot failed <<\n\n")
                    return
        self.progress.emit(100)

class AsStepEnable(QCheckBox):
    enableChanged=QtCore.pyqtSignal(str,bool)
    def __init__(self,text,parent=None):
        super(QCheckBox, self).__init__(text,parent)
        self.stateChanged.connect(self.on_stateChanged)
    def on_stateChanged(self,state):
        self.enableChanged.emit(self.text(),state)
        
class UIFlashloader(QWidget):
    def __init__(self, parent=None):
        super(QWidget, self).__init__(parent)
        
        self.loader = AsFlashloader()
        self.loader.infor.connect(self.on_loader_infor)
        self.loader.progress.connect(self.on_loader_progress)
        
        vbox = QVBoxLayout()
        
        grid = QGridLayout()
        grid.addWidget(QLabel('Application'),0,0)
        self.leApplication = QLineEdit()
        grid.addWidget(self.leApplication,0,1)
        self.btnOpenApp = QPushButton('...')
        grid.addWidget(self.btnOpenApp,0,2)

        grid.addWidget(QLabel('Flash Driver'),1,0)
        self.leFlsDrv = QLineEdit()
        grid.addWidget(self.leFlsDrv,1,1)
        self.btnOpenFlsDrv = QPushButton('...')
        grid.addWidget(self.btnOpenFlsDrv,1,2)

        grid.addWidget(QLabel('Progress'),2,0)
        self.pgbProgress = QProgressBar()
        self.pgbProgress.setRange(0,100)
        grid.addWidget(self.pgbProgress,2,1)
        self.btnStart=QPushButton('Start')
        grid.addWidget(self.btnStart,2,2)
        
        grid.addWidget(QLabel('aslua bootloader:'),3,0)
        self.cmbxCanDevice = QComboBox()
        self.cmbxCanDevice.addItems(['socket','serial','vxl','peak','tcp'])
        self.cmbxCanPort = QComboBox()
        self.cmbxCanPort.addItems(['port 0','port 1','port 2','port 3','port 4','port 5','port 6','port 7'])
        self.cmbxCanBaud = QComboBox()
        self.cmbxCanBaud.addItems(['125000','250000','500000','1000000','115200'])
        self.btnStartASLUA=QPushButton('Start')
        grid.addWidget(self.cmbxCanDevice,3,1)
        grid.addWidget(self.cmbxCanPort,3,2)
        grid.addWidget(self.cmbxCanBaud,3,3)
        grid.addWidget(self.btnStartASLUA,3,4)
        vbox.addLayout(grid)
        
        hbox = QHBoxLayout()
        vbox2 = QVBoxLayout()
        for s in self.loader.GetSteps():
            cbxEnable = AsStepEnable(s[0])
            cbxEnable.setChecked(s[1])
            cbxEnable.enableChanged.connect(self.on_enableChanged)
            vbox2.addWidget(cbxEnable)
        hbox.addLayout(vbox2)
        self.leinfor = QTextEdit()
        self.leinfor.setReadOnly(True)
        hbox.addWidget(self.leinfor)
        
        vbox.addLayout(hbox)
        
        self.setLayout(vbox)
        
        self.btnOpenApp.clicked.connect(self.on_btnOpenApp_clicked)
        self.btnOpenFlsDrv.clicked.connect(self.on_btnOpenFlsDrv_clicked)
        self.btnStart.clicked.connect(self.on_btnStart_clicked)
        self.btnStartASLUA.clicked.connect(self.on_btnStartASLUA_clicked)
        
        release = os.path.abspath('%s/../../../release'%(os.curdir))
        default_app=''
        default_flsdrv=''
        if(os.path.exists(release)):
            for ss in glob.glob('%s/ascore/*.s19'%(release)):
                default_app = ss
                break
            for ss in glob.glob('%s/asboot/*-flsdrv.s19'%(release)):
                default_flsdrv = ss
                break
        if(os.path.exists(default_app)):
            self.leApplication.setText(default_app)
        if(os.path.exists(default_flsdrv)):
            self.leFlsDrv.setText(default_flsdrv)

    def on_enableChanged(self,step,enable):
        self.loader.SetEnable(step, enable)

    def on_loader_infor(self,text):
        self.leinfor.append(text)
    
    def on_loader_progress(self,prg):
        self.pgbProgress.setValue(prg)

    def on_btnOpenApp_clicked(self):
        rv = QFileDialog.getOpenFileName(None,'application file', '','application (*.s19 *.bin)')
        self.leApplication.setText(rv[0])

    def on_btnOpenFlsDrv_clicked(self):
        rv = QFileDialog.getOpenFileName(None,'flash driver file', '','flash driver (*.s19 *.bin)')
        self.leFlsDrv.setText(rv[0])

    def on_btnStart_clicked(self):
        if(os.path.exists(str(self.leApplication.text()))):
            self.pgbProgress.setValue(1)
            self.loader.setTarget(str(self.leApplication.text()), str(self.leFlsDrv.text()))
            self.loader.start()
        else:
            QMessageBox.information(self, 'Tips', 'Please load a valid application first!')

    def on_btnStartASLUA_clicked(self):
        aslua = os.path.abspath('%s/pyas/aslua.exe'%(os.curdir))
        fbl = os.path.abspath('%s/pyas/flashloader.lua'%(os.curdir))
        cmd = '%s %s %s %s %s %s %s'%(aslua, fbl, self.leFlsDrv.text(), self.leApplication.text(),
                             self.cmbxCanDevice.currentText(),
                             str(self.cmbxCanPort.currentText()).replace('port',''),
                             self.cmbxCanBaud.currentText())
        print(cmd)
        self.leinfor.append(cmd+'\n')
        if(0 == os.system(cmd)):
            self.leinfor.append('run aslua bootloader done successfully!')
        else:
            self.leinfor.append('run aslua bootloader done failed!')
