# KR ATE functions
# history (in reverse order)
# shared history with krate_cl.py (look there)

import math, glob, os, serial, time

def krate_version():
    krate_vxpxx=0.82
    return ("krate v%0.2f 04/01/2014, (c) 2011-2014 by KR" % krate_vxpxx)

class FraData(object):
    def __init__(self,name="",legend="", datetimestr=""):
        self.name=name
        self.legend=legend
        self.datetimestr=datetimestr
        self.dut=""
        self.frasetup=""
        self.author=""
        self.valid=False
        self.sweep_var=""
        self.sweep_value=0.0
        self.sweep_unit=""
        self.frdata=[]
    def __del__(self):
        self.valid=False
    def add_frdata(self,frdata=[]):
        if len(frdata)>0 and len(frdata)<(1<<15):
            self.frdata=list(frdata)
            self.valid=True
        else:
            self.valid=False
        return self.valid
    def frdata_get_f(self):
        f=[]
        for ftuple in self.frdata:
            f.append(ftuple[0])
        return f
    def frdata_ph_adjust(self,ph):
        ph_adjusted=list(ph)
        ph_revelations=0
        for i in range(1,len(ph)):
            if (ph[i]-ph[i-1])>180:
                ph_revelations-=1
##                        print "- i=%d ph_revelations=%d phn=%0.1f, phn-1=%0.1f" % (i,ph_revelations,ph[i],ph[i-1])
            elif (ph[i]-ph[i-1])<-180:
                ph_revelations+=1
##                        print "+ i=%d ph_revelations=%d phn=%0.1f, phn-1=%0.1f" % (i,ph_revelations,ph[i],ph[i-1])
            ph_adjusted[i]=ph[i]+360*ph_revelations
        return ph_adjusted
    def frdata_get_f_db_ph(self,ph_adjust=True):
        f=[]; db=[]; ph=[]
        for ftuple in self.frdata:
            f.append(ftuple[0]); db.append(ftuple[3]); ph.append(ftuple[4])
        if ph_adjust:
            ph_adjusted=self.frdata_ph_adjust(ph)
            return (f,db,ph_adjusted)
        else:
            return (f,db,ph)
    def fr_data_det_pm(self):
        pm=359.9; fpm=0
        (f,db,ph)=self.frdata_get_f_db_ph()
        if len(f)>1:
            for i in range (0,len(f)-1):
                # detect 0dB crossing
                if cmp(db[i],0)!=cmp(db[i+1],0):
                    # linear interpolation of fc and pm
                    delta_f=f[i+1]-f[i]
                    delta_db=db[i+1]-db[i]
                    delta_ph=ph[i+1]-ph[i]
                    fc=f[i]+abs(db[i])/abs(delta_db)*delta_f
                    phfc=(ph[i]+(fc-f[i])/delta_f*delta_ph)%360
                    # print "fcprior=%.1fHz fc=%.1fHz delta_f=%.1fHz delta_db=%.3fdB" % (f[i],fc,delta_f,delta_db)
                    if pm==None or pm>phfc:
                        pm=phfc; fpm=fc
        return (pm,fpm)
    def fr_data_det_gm(self):
        gm=-999.999; fgm=0
        (f,db,ph)=self.frdata_get_f_db_ph()
        if len(f)>1:
            for i in range (0,len(f)-1):
                # detect phase crossing
                if abs((ph[i]%360)-(ph[i+1]%360))>180:
                    # linear interpolation of gm and fgm
                    delta_f=f[i+1]-f[i]
                    delta_db=db[i+1]-db[i]
                    delta_ph=min((ph[i+1]-ph[i])%360,(ph[i]-ph[i+1])%360)
                    dist_ph=min((ph[i])%360,(-ph[i])%360)
                    dist_f=delta_f*dist_ph/delta_ph
                    dist_db=delta_db*dist_ph/delta_ph
                    # print "detected phase jump at %.1f delta_ph=%1fdeg dist_ph=%1fdeg" % (f[i],delta_ph,dist_ph)
                    if gm==None or (db[i]+dist_db)>gm:
                        gm=(db[i]+dist_db); fgm=f[i]+dist_f
        # sign-correct gm
        return (-gm,fgm)
            
class Vin(object):
    nof=0
    def __init__(self,namestr="", addr=0):
        Vin.nof+=1
        self.alive=False
        self.instr_name=namestr
        self.serobject=None
        self.ifname="/dev/tbd"
        self.iftype="tbd"
        self.errors=0
        self.timeout=0.3
        self.command_delay=0.01
        self.addr=addr
    def __del__(self):
        Vin.nof-=1
    def ifclose(self):
        if self.serobject:
            self.alive=False
            self.serobject.close()
            self.serobject=None
    def ifopen(self):
        # if self.seroject exists, close it and none it
        if self.serobject:
            self.serobject.close()
            self.serobject=None
        try:
            if "rs232" in self.iftype:
                self.serobject=serial.Serial(self.ifname,baudrate=19200, bytesize=8, parity='N', stopbits=1, timeout=self.timeout, xonxoff=0, rtscts=0)
            else:
                self.serobject=None
                self.ifname="/dev/tbd"
                self.iftype="tbd"
        except:
            # problem while opening, clear all if
            self.alive=False
            self.serobject=None
            self.ifname="/dev/tbd"
            self.iftype="tbd"
    def clear_rbuffer(self):
        # clear receive buffer, expect to run into timeout
        rec=self.serobject.read(1<<10)
    def sendbinary(self,m,wait4receipt=True):
        if self.alive:
            while True:
                for i in m:
                    self.serobject.write(chr(i))
                if wait4receipt:
                    time.sleep(self.command_delay)
                    rec=self.serobject.read(26)
                    recb=[]
                    for i in rec:
                        recb.append(ord(i))
                    if len(recb)<4 or recb[3]!=0x80:
                        # print "Opps, Vin instrument '%s' returned:\n" % self.instr_name
                        # print recb
                        # let's try to fix it. clear buffer (expect timeout)
                        self.clear_rbuffer()
                        self.errors+=1
                        # allow 2 subsequent errors, until presumed dead
                        if self.errors>2:
                            self.alive=False
                            break
                    else:
                        self.errors=0
                        break
                else:
                    break
    def receivebinary(self):
        time.sleep(self.command_delay)
        rec=self.serobject.read(26)
        m=[]
        for i in rec:
            m.append(ord(i))
        if len(m)<4 or m[3]!=0x80:
            # print "Opps, Vin instrument '%s' returned:\n" % self.instr_name
            # print m
            # let's try to fix it. clear buffer (expect timeout)
            rec=self.serobject.read(1<<10)
            self.errors+=1
            # allow 2 subsequent errors, until presumed dead
            if self.errors>2:
                self.alive=False
        else:
            self.errors=0
        return m
    def remote_on(self):
        m=self.message_new(self.addr,cmd=0x20,par=1)
        self.sendbinary(m, wait4receipt=True)
    def remote_off(self):
        m=self.message_new(self.addr,cmd=0x20,par=0)
        self.sendbinary(m, wait4receipt=False)
    def output(self,on=0):
        m=self.message_new(self.addr,cmd=0x21,par=on)
        self.sendbinary(m, wait4receipt=True)
    def conf_vin(self,vo=0):
        m=self.message_new(self.addr,cmd=0x23,par=int(vo*1000))
        self.sendbinary(m, wait4receipt=True)
    def conf(self,vo=0,vomax=0,iomax=0):
        m=self.message_new(self.addr,cmd=0x22,par=int(vomax*1000))
        self.sendbinary(m, wait4receipt=True)
        m=self.message_new(self.addr,cmd=0x23,par=int(vo*1000))
        self.sendbinary(m, wait4receipt=True)
        m=self.message_new(self.addr,cmd=0x24,par=int(iomax*1000))
        self.sendbinary(m, wait4receipt=True)
    def message_with_checksum(self,m):
        checksum=0
        for i in range(0,len(m)-1):
            checksum+=m[i]
        m[-1]=checksum%256
        return m
    def message_new(self,addr=0,cmd=0x20,par=0):
        m=[0]*26; m[0]=0xaa; m[1]=addr%256; m[2]=cmd%256
        m[3]=par%256;m[4]=(par>>8)%256;m[5]=(par>>16)%256;m[6]=(par>>24)%256
        return self.message_with_checksum(m)

def vin_find(Vin,Fra):
    Vin.__init__(addr=0)
    # look for usb-rs232 interface ("Prolific"), but not used by Fra
    for dev in find_usb_serial_devices():
        if 'Prolific' in dev[1]:
            if dev[0] in Fra.ifname:
                # instrument already used by Fra, skip
                pass
            else:
                Vin.alive=True
                Vin.instr_name="BK 178x Programmable DC Power Supply"
                Vin.ifname=dev[0]
                Vin.iftype="rs232"
    # if an instrument was found, permanently open it, determine name and version
    if Vin.alive:
        Vin.ifopen()
    return

class Smbb(object):
    nof=0
    def __init__(self,namestr="", addr=0):
        Smbb.nof+=1
        self.alive=False
        self.instr_name=namestr
        self.serobject=None
        self.ifname="/dev/tbd"
        self.iftype="tbd"
        self.errors=0
        self.timeout=0.3
        self.command_delay=0.01
        self.addr_pmbus=[]
        self.addr_pmbus_active=None
        self.addr_pmbus_ara=[]
        self.answer_delimiter=" "
    def __del__(self):
        Smbb.nof-=1
    def ifclose(self):
        if self.serobject:
            self.alive=False
            self.serobject.close()
            self.serobject=None
    def ifopen(self):
        # if self.seroject exists, close it and none it
        if self.serobject:
            self.serobject.close()
            self.serobject=None
        try:
            if "ttyacm" in self.iftype:
##                print "trying to talk to '%s'" % self.ifname
                self.serobject=serial.Serial(self.ifname,baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=self.timeout, xonxoff=0, rtscts=0)
##                if self.serobject:
##                    print "after opening..."
            else:
                self.serobject=None
                self.ifname="/dev/tbd"
                self.iftype="tbd"
        except:
            # problem while opening, clear all if
            self.alive=False
            self.serobject=None
            self.ifname="/dev/tbd"
            self.iftype="tbd"
    def ifflush(self):
      if self.serobject:
	self.serobject.flushInput()
	self.serobject.flushOutput()
    def set_instr_name(self):
        if self.serobject:
	    # at this stage we don't know which smbb bridge is in use, so ver needs to work for all devices (mbed, u2i)
	    self.serobject.write("ver\n")
	    s=self.serobject.readline() # flush garbage
	    self.serobject.write("ver\n")
	    s=self.serobject.readline()
            self.instr_name=s.strip()
            if s:
                self.alive=True
            else:
                self.alive=False
            if "u2i" in s:
	      # if u2i, set transmission speed to 400kb/s
	      self.serobject.write("f %x\n" % 400)
	      s=self.serobject.readline()
	      # if u2i, clear fault LEDs
	      self.serobject.write("z 1\n")
	      s=self.serobject.readline()
	      self.answer_delimiter=", "	# u2i answer delimiter
	    else:
	      self.answer_delimiter=" "		# mbed smbb answer delimiter
        else:
            self.alive=False
    def scan_pmbus_addresses(self):
        if self.serobject and self.alive:
            self.addr_pmbus=[]
            self.addr_pmbus_active=None
            if "u2i" in self.instr_name:
	      # Arduino u2i
	      self.serobject.write("s 10 7F\n")
	      s=self.serobject.readline().strip().strip("[]");
	      # print "u2i stripped address string '%s'" % s
	      if s:
		self.addr_pmbus=list([int(i,16) for i in s.split(self.answer_delimiter)])
		self.addr_pmbus_active=self.addr_pmbus[0]
	      else:
		self.addr_pmbus=list()
		self.addr_pmbus_active=None
	      self.serobject.write("z 1\n")
	      s=self.serobject.readline()
	    else:
	      # mbed smbb
	      self.serobject.write("scan 10 7F\n")
	      s=self.serobject.readline().strip()
	      # print "received address string '%s'" % s
	      try:
		  for addr in s:
		      self.addr_pmbus=list([int(i,16) for i in s.split(self.answer_delimiter)])
		  if len(self.addr_pmbus)>0:
		      self.addr_pmbus_active=self.addr_pmbus[0]
	      except:
		  self.addr_pmbus=list()
		  self.addr_pmbus_active=None
		  self.alive=False
		  # print "received address string '%s' hence device interface is assumed not alive" % s
    def pmbus_ara(self):
	self.addr_pmbus_ara=[]
	if "u2i" in self.instr_name:
	  self.serobject.write("l\n")
	  s=self.serobject.readline().strip().strip("[]");
	  answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
	  if answer[0]==0:
	    self.serobject.write("l 1\n")
	    s=self.serobject.readline().strip().strip("[]");
	    try:
	      self.addr_pmbus_ara=list([int(i,16) for i in s.split(self.answer_delimiter)])
	    except:
	      self.addr_pmbus_ara=list()
	      self.addr_pmbus_active=None
	      self.alive=False
	  else:
	    # SALRT is currently high, i.e. erase ARA list
            self.addr_pmbus_ara=[]
    def pmbus_address_set(self):
        if self.serobject and self.alive and self.addr_pmbus_active:
	    # addr 0xyy works for both mbed as well as u2i
            self.serobject.write("addr %02x\n"%self.addr_pmbus_active)
            # smbb and u2i respond with address, ignore
            s=self.serobject.readline()
    def pmbus_read_fw_version(self):
        if  self.serobject and self.alive:
            # READ_FW_VERSION
            # returns lsb msb with lsb=version and msb representing "F", or "B", or "A", or "I", or "S"
            self.serobject.write("r E0 2\n")
            s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
            try:
		answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                if len(answer)==2:
                    fw_str="%c%03d" % (answer[1],answer[0])
                else:
                    fw_str="FW:unknown"
                return(fw_str)
            except:
                return("")
    def pmbus_read_dsp_version(self):
        if  self.serobject and self.alive:
            # READ_DSP_VERSION
            # returns block of 5 bytes, with 04 b0 b1 b2 b3, b0/b1 dsp version tag, and b2/b3 version value
            self.serobject.write("r E5 5\n")
            s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
            # print "DSP_VERSION returned the data: '%s'" % s
            try:
		answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                if len(answer)==5:
                    dsp_str="D%03d" % (answer[3]+answer[4]*256)
                else:
                    dsp_str="DSP:unknown"
                return(dsp_str)
            except:
                return("")
    def pmbus_read_hw_version(self):
        if  self.serobject and self.alive:
            # READ_HW_VERSION
            # returns lsb representing HW version, [7:4] major, [3:0] minor
            self.serobject.write("r E1 1\n")
            s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
            try:
		answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                if len(answer)==1:
                    hw_str="HW%01d.%01d" % (int(answer[0])/16,int(answer[0])%16)
                else:
                    hw_str="HW:unknown"
                return(hw_str)
            except:
                return("")
    def pmbus_icmfr_info(self):
        if  self.serobject and self.alive:
            # ICMFR_INFO
            # returns lsb msb with lsb=01 (count), and msb='B' for BL, or 'F', or...
            self.serobject.write("r D8 2\n")
            s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
            try:
		answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                if len(answer)==2:
                    icmfr_info_str="%c" % (answer[1])
                else:
                    icmfr_info_str="X"
                return(icmfr_info_str)
            except:
                return("")
    def pmbus_status_word(self):
        if  self.serobject and self.alive:
            self.serobject.write("r 79 2\n")
            s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
            try:
		answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                if len(answer)==2:
                    status=answer[0]+answer[1]*256
                else:
                    status=-1
                return(status)
            except:
                return -1;
    def pmbus_clear_faults(self):
        if  self.serobject and self.alive:
            self.serobject.write("w 03\n")
            s=self.serobject.readline().strip()
        return
    def pmbus_operation(self,op_value):
        if  self.serobject and self.alive:
            self.serobject.write("w 01 %02x\n" % op_value)
            s=self.serobject.readline().strip()
        return
    def pmbus_read_vin(self):
        if  self.serobject and self.alive:
            self.serobject.write("r 88 2\n")
            s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
            try:
		answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                if len(answer)==2:
                    vin=self.pmbus_q15_0(answer[0],answer[1])/1862.0
                else:
                    vin=None
                return(vin)
            except:
                return None;
    def pmbus_read_vout(self):
        if  self.serobject and self.alive:
            self.serobject.write("r 8B 2\n")
            s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
            try:
		answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                if len(answer)==2:
                    vout=self.pmbus_q15_0(answer[0],answer[1])/640.0
                else:
                    vout=None
                return(vout)
            except:
                return None;
    def pmbus_read_iout(self):
        if  self.serobject and self.alive:
            self.serobject.write("r 8C 2\n")
            s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
            try:
		answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                if len(answer)==2:
                    iout=self.pmbus_q15_0(answer[0],answer[1])/10.24
                else:
                    iout=None
                return(iout)
            except:
                return None;
    def pmbus_read_duty_cycle(self):
        if  self.serobject and self.alive:
            self.serobject.write("r 94 2\n")
            s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
            try:
		answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                if len(answer)==2:
                    d=self.pmbus_q15_0(answer[0],answer[1])/10.0
                else:
                    d=None
                return(d)
            except:
                return None;
    def pmbus_read_frequency(self):
        if  self.serobject and self.alive:
            self.serobject.write("r 95 2\n")
            s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
            try:
		answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                if len(answer)==2:
                    f=self.pmbus_q15_0(answer[0],answer[1])/32.0
                else:
                    f=None
                return(f)
            except:
                return None;
    def pmbus_read_nof_phases(self):
        if  self.serobject and self.alive:
            self.serobject.write("r E6 2\n")
            s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
            try:
		answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                if len(answer)==2:
                    ph_field=(self.pmbus_q15_0(answer[0],answer[1]) & 0x30)>>4
                    if ph_field==0:
                        # single-phase single-sampling PWM
                        nof_phases=1
                    elif ph_field==2:
                        # dual-phase PWM
                        nof_phases=2
                    elif ph_field==3:
                        # single-phase dual-sampling PWM
                        nof_phases=1
                    else:
                        nof_phases=None
                else:
                    nof_phases=None
                return(nof_phases)
            except:
                return None;
    def pmbus_read_temp(self,sensor=1):
        if  self.serobject and self.alive:
            if sensor==2:
                command=0x8E
            elif sensor==3:
                command=0x8F
            else:
                command=0x8D
            self.serobject.write("r %02X 2\n"%command)
            s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
            try:
		answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                if len(answer)==2:
                    temp=self.pmbus_q15_0(answer[0],answer[1])/1.0
                else:
                    temp=None
                return(temp)
            except:
                return None;
    def pmbus_vout_command(self,vo=0):
        if  self.serobject and self.alive:
            if vo>=0.1 and vo<=5.6:
                voint=int(vo*5120.0)
                volsb=voint%256
                vomsb=voint>>8
                # print "vomsb=%02x volsb=%02x" % (vomsb,volsb)
                self.serobject.write("w 21 %02X %02X\n"%(volsb,vomsb))
                s=self.serobject.readline().strip()
            else:
                pass
            return
    def pmbus_frequency_switch(self,fsw=None):
        if  self.serobject and self.alive:
            if fsw==None:
                # fsw not provided, read frequency_switch
                self.serobject.write("r 33 2\n")
                s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
                try:
		    answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                    if len(answer)==2:
                        f=answer[0]+answer[1]*256
                    else:
                        f=None
                    return(f)
                except:
                    return None;
            else:
                if fsw>=250 and fsw<=1000:
                    self.serobject.write("w 33 %02X %02X\n"%(int(fsw%256),int(fsw>>8)))
                    s=self.serobject.readline().strip()
            return
    def pmbus_general_settings(self,new_general_settings=None):
        if  self.serobject and self.alive:
            if new_general_settings==None:
                # new_general_settings not provided, just read
                self.serobject.write("r E6 2\n")
                s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
                try:
		    answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                    if len(answer)==2:
                        gs=answer[0]+answer[1]*256
                    else:
                        gs=None
                    return(gs)
                except:
                    return None;
            else:
                # write general settings
                self.serobject.write("w E6 %02X %02X\n"%(int(new_general_settings%256),int(new_general_settings>>8)))
                s=self.serobject.readline().strip()
            return
    def pmbus_phases(self,nof_phases=None):
        if  self.serobject and self.alive:
            if nof_phases==None:
                # nof_phases not provided, just read
                gs=self.pmbus_general_settings()
                # print "gs=0x%04x" % gs
                if ((gs>>4)&3)==2:
                    nof_phases=2
                else:
                    nof_phases=1
                return(nof_phases)
            else:
                gs=self.pmbus_general_settings()
                if nof_phases==1:
                    gs=(gs&0xffcf)|0x30
                else:
                    gs=(gs&0xffcf)|0x20
                # print "gs=0x%04x" % gs
                self.pmbus_general_settings(gs)
            return
    def pmbus_hal(self,hal_addr,hal_data=None):
        # r/w access to a hal register
        if  self.serobject and self.alive:
            self.serobject.write("w E7 %02X %02X\n" % (int(hal_addr%256),int(hal_addr>>8)) )
            s=self.serobject.readline().strip()
            if hal_data==None:
                # HAL read access
                self.serobject.write("r E8 2\n")
                s=self.serobject.readline().strip().strip("[]")	# u2i delivers answer in brackets
                try:
		    answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                    if len(answer)==2:
                        response=answer[0]+answer[1]*256
                    else:
                        response=None
                    return(response)
                except:
                    return None;
            else:
                # HAL write access
                # print "HAL register %d=0x%04X" % (hal_addr,hal_data)
                self.serobject.write("w E8 %02X %02X\n" % (int(hal_data%256),int(hal_data>>8)) )
                s=self.serobject.readline().strip()
    def pmbus_ambareg(self,amba_addr,amba_data=None):
        # r/w access to a ambareg register
        if  self.serobject and self.alive:
            self.serobject.write("w D0 %02X %02X\n" % (int(amba_addr%256),int(amba_addr>>8)) )
            s=self.serobject.readline().strip()
            if amba_data==None:
                # AMBAREG_W read access
                self.serobject.write("r D3 2\n")
                s=self.serobject.readline().strip().strip("[]")
                try:
		    answer=list([int(i,16) for i in s.split(self.answer_delimiter)])
                    if len(answer)==2:
                        response=answer[0]+answer[1]*256
                    else:
                        response=None
                    return(response)
                except:
                    return None;
            else:
                # AMBAREG_W read access
                self.serobject.write("w D3 %02X %02X\n" % (int(amba_data%256),int(amba_data>>8)) )
                s=self.serobject.readline().strip()
    def statr2(self,amba_addr,nof_reads,timeout_statr2):
        # statistical read access (word) returning min, max and avg
        if  self.serobject and self.alive:
            self.serobject.write("w D0 %02X %02X\n" % (int(amba_addr%256),int(amba_addr>>8)) )
            s=self.serobject.readline().strip().strip("[]")
            if "u2i" in self.instr_name:
	      self.serobject.write("t D3 %x\n" % nof_reads)
	      time_spent=0.0
	      s=""
	      while ( (s=="") & (time_spent<timeout_statr2) ):
		  time.sleep(0.1)
		  time_spent=time_spent+0.1
		  s=self.serobject.readline().strip().strip("[]")
	      s_data=s.split(self.answer_delimiter)
	      if len(s_data)==3:
		  s_data_conv=[ eval("0x"+s_data[0]),eval("0x"+s_data[1]),float(s_data[2]) ]
	      else:
		  s_data_conv=None
	      return s_data_conv
	    else:
	      self.serobject.write("statr2 D3 %f\n" % nof_reads)
	      time_spent=0.0
	      s=""
	      while ( (s=="") & (time_spent<timeout_statr2) ):
		  time.sleep(0.1)
		  time_spent=time_spent+0.1
		  s=self.serobject.readline().strip()
	      s_data=s.split(" ")
	      if len(s_data)==3:
		  s_data_conv=[ eval("0x"+s_data[0]),eval("0x"+s_data[1]),float(s_data[2]) ]
	      else:
		  s_data_conv=None
	      return s_data_conv
    def pmbus_devinfo(self):
        # try to compile smbus device info, consisting of FW/DSP/HW and Status Word information
        if  self.serobject and self.alive:
            icmfrstr=self.pmbus_icmfr_info()
            if icmfrstr.upper()=="F" or icmfrstr.upper()=="S":
                fwstr=self.pmbus_read_fw_version()
                dspstr=self.pmbus_read_dsp_version()
                hwstr=self.pmbus_read_hw_version()
                statusstr="Status=0x%04X" % self.pmbus_status_word()
            elif icmfrstr=="":
                fwstr="No device recognised"
                dspstr=""
                hwstr=""
                statusstr=""
            else:
                fwstr="Bootloader"
                dspstr=""
                hwstr=""
                statusstr=""
            return (fwstr+" "+dspstr+" "+hwstr+" "+statusstr)
        else:
            return ("No interface available")
    def pmbus_devtele(self):
        # compile smbus device telemetry info: vo
        if  self.serobject and self.alive:
            vin=self.pmbus_read_vin()
            if vin<>None:
                vinstr="Vin=%.3fV" % vin
            else:
                vinstr=""
            vo=self.pmbus_read_vout()
            if vo<>None:
                vostr="Vo=%.3fV" % vo
            else:
                vostr=""
            io=self.pmbus_read_iout()
            if io<>None:
                iostr="Io=%.3fA" % io
            else:
                iostr=""
            tempstr=""
            for temp_sensor in [1,2,3]:
                temp=self.pmbus_read_temp(temp_sensor)/1.0
                if temp<>None:
                    tempstr=tempstr+" T%d=%.0fdegC" % (temp_sensor,temp)
                else:
                    tempstr=" "
                    break
            tempstr=tempstr.strip()
            d=self.pmbus_read_duty_cycle()
            if d<>None:
                dstr="d=%.1f%%" % d
            else:
                dstr=""
            f=self.pmbus_read_frequency()
            if f<>None:
                fstr="f=%.1fkHz" % f
            else:
                fstr=""
            nof_ph=self.pmbus_read_nof_phases()
            if nof_ph<>None:
                phstr="ph=%.0d" % nof_ph
            else:
                phstr=""
            return vinstr+" "+vostr+" "+iostr+" "+fstr+" "+phstr+" "+dstr+" "+tempstr
        else:
            return ("No interface available")

    def pmbus_q15_0(self,lsb=0,msb=0):
        uint16=int(lsb)%256+(int(msb)%256)*256
        if uint16<(1<<15):
            return uint16
        else:
            return uint16-(1<<16)

def smbb_find(Smbb):
    Smbb.__init__(addr=0)
    # look for usb ttyACM device (as used by multifunctional mbed and Arduino devices)
    for dev in find_usb_serial_devices():
        if 'ttyacm' in dev[1]:
            Smbb.alive=True
            Smbb.ifname=dev[0]
            Smbb.iftype="ttyacm"
    # if an instrument was found, permanently open it, determine name and version
    if Smbb.alive:
        Smbb.ifopen()
    if Smbb.alive:
        Smbb.set_instr_name()
        Smbb.scan_pmbus_addresses()
        Smbb.pmbus_ara()
    return

class Load(object):
    nof=0
    def __init__(self,namestr="", addr=22):
        Load.nof+=1
        self.alive=False
        self.instr_name=namestr
        self.instr_version=""
        self.serobject=None
        self.ifname="/dev/tbd"
        self.iftype="tbd"
        self.errors=0
        self.timeout=1
        self.addr=addr
        self.command_delay=0.05
    def __del__(self):
        Load.nof-=1
    def ifclose(self):
        if self.serobject:
            self.alive=False
            self.serobject.close()
            self.serobject=None
    def ifopen(self):
        try:
            if "prologix-gpib" in self.iftype:
                self.serobject=serial.Serial(self.ifname,timeout=self.timeout)
            else:
                self.serobject=None
                self.ifname="/dev/tbd"
                self.iftype="tbd"
        except:
            # problem while opening, clear all if
            self.alive=False
            self.serobject=None
            self.ifname="/dev/tbd"
            self.iftype="tbd"
    def set_addr(self):
        if "prologix-gpib" in self.iftype:
            self.serobject.write("++auto 0\n")
            self.serobject.write("++addr %s\n" % str(self.addr))
            # turn off automatic talk after listen (Agilent doesn't like it, this also works for Tektronix)
    def set_instr_name(self):
        if self.serobject:
            self.set_addr()
            self.serobject.write("*IDN?\n")
            self.serobject.write("++read\n")
            s=self.serobject.readline()
            self.instr_name=s.strip()
            if s:
                self.alive=True
            else:
                self.alive=False
        else:
            self.alive=False
    def output(self,on="off"):
        if self.alive:
            self.set_addr()
            if "ON" in on.upper():
                if "TEKTRONIX" in self.instr_name:
                    self.serobject.write("OUTPUT1:STATE ON\n")
                else: # assume Agilent by default
                    self.serobject.write("OUTPUT ON\n")
            else:
                if "TEKTRONIX" in self.instr_name:
                    self.serobject.write("OUTPUT1:STATE OFF\n")
                else: # assume Agilent by default
                    self.serobject.write("OUTPUT OFF\n")
    def conf_static(self,io_static,v_scale,v_offset):
        if self.alive:
            self.set_addr()
            v_static=v_offset+io_static*v_scale
            if "TEKTRONIX" in self.instr_name:
                self.serobject.write("OUTP1:IMP 50\n")
                self.serobject.write("OUTP1:POL NORM\n")
                self.serobject.write("SOUR1:AM:STAT OFF\n")
                self.serobject.write("SOUR1:FM:STAT OFF\n")
                self.serobject.write("SOUR1:PM:STAT OFF\n")
                self.serobject.write("SOUR1:PWM:STAT OFF\n")
                self.serobject.write("SOUR1:BURST:STAT OFF\n")
                self.serobject.write("SOUR1:VOLT:UNIT VPP\n")
                self.serobject.write("SOUR1:FUNC:SHAP DC\n")
                self.serobject.write("SOUR1:VOLT:LIM:HIGH 5V\n")
                self.serobject.write("SOUR1:VOLT:LIM:LOW 0V\n")
                self.serobject.write("SOUR1:VOLT:IMM:OFFSET %f\n" %v_static)
                #self.serobject.write("SOUR1:VOLT:IMM:HIGH 1V\n")
                #self.serobject.write("SOUR1:VOLT:IMM:LOW 0V\n")
            else:
                self.serobject.write("BURST:STATE OFF\n")
                self.serobject.write("SWEEP:STATE OFF\n")
                self.serobject.write("FUNCTION DC\n")
                self.serobject.write("VOLTAGE:OFFSET %f\n" %v_static)
    def conf_pulse(self,ioh,iol,ioton,iotper,iosr,v_scale,v_offset):
        if self.alive:
            self.set_addr()
            vh=v_offset+ioh*v_scale
            vl=v_offset+iol*v_scale
            trise=(ioh-iol)/(iosr/1e-6)*0.8
            # print "debug: ioh=%f iol=%f sr=%f trise=%e" % (ioh,iol,iosr,trise)
            if "TEKTRONIX" in self.instr_name:
                self.serobject.write("OUTP1:IMP 50\n")
                self.serobject.write("OUTP1:POL NORM\n")
                self.serobject.write("SOUR1:AM:STAT OFF\n")
                self.serobject.write("SOUR1:FM:STAT OFF\n")
                self.serobject.write("SOUR1:PM:STAT OFF\n")
                self.serobject.write("SOUR1:PWM:STAT OFF\n")
                self.serobject.write("SOUR1:BURST:STAT OFF\n")
                self.serobject.write("SOUR1:FREQ:MODE FIX\n")
                self.serobject.write("SOUR1:VOLT:UNIT VPP\n")
                self.serobject.write("SOUR1:FUNC:SHAP PULSE\n")
                self.serobject.write("SOUR1:VOLT:LIM:HIGH 5V\n")
                self.serobject.write("SOUR1:VOLT:LIM:LOW 0V\n")
                self.serobject.write("SOUR1:VOLT:IMM:HIGH %f\n" %vh)
                self.serobject.write("SOUR1:VOLT:IMM:LOW  %f\n" %vl)
                self.serobject.write("SOUR1:PULS:PER  %e\n" %iotper)
                self.serobject.write("SOUR1:PULS:WIDT  %e\n" %ioton)
                self.serobject.write("SOUR1:PULS:TRAN:LEAD  %e\n" %trise)
                self.serobject.write("SOUR1:PULS:TRAN:TRA  %e\n" %trise)
            else:
                self.serobject.write("SWEEP:STATE OFF\n")
                self.serobject.write("BURST:STATE OFF\n")
                self.serobject.write("FUNCTION PULSE\n")
                self.serobject.write("VOLTAGE:HIGH %f\n" %vh)
                self.serobject.write("VOLTAGE:LOW %f\n" %vl)
                self.serobject.write("PULSE:WIDTH %f\n" %ioton)
                self.serobject.write("PULSE:PERIOD %f\n" %iotper)
                self.serobject.write("PULSE:TRANSITION %f\n" %trise)
    def conf_burst(self,burst_count=1,burst_period=1.0):
        if self.alive:
            self.set_addr()
            if "TEKTRONIX" in self.instr_name:
                self.serobject.write("TRIG:SEQ:SOUR TIM\n")
                self.serobject.write("TRIG:SEQ:TIM %e\n" %burst_period)
                self.serobject.write("SOUR1:BURST:MODE TRIG\n")
                self.serobject.write("SOUR1:BURST:NCYC %e\n" %burst_count)
                self.serobject.write("SOUR1:BURST:STAT ON\n")
            else:
                self.serobject.write("BURST:MODE TRIG\n")
                self.serobject.write("BURST:NCYC %d\n" %burst_count)
                self.serobject.write("BURST:INT:PER %f\n" %burst_period)
                self.serobject.write("BURST:STATE ON\n")
    def conf_sr(self,ioh,iol,iosr,v_scale,v_offset):
        if self.alive:
            self.set_addr()
            vh=v_offset+ioh*v_scale
            vl=v_offset+iol*v_scale
            trise=(ioh-iol)/(iosr/1e-6)*0.8
            if "TEKTRONIX" in self.instr_name:
                #print "Debug: Serial flushInOutput requested prior to setting SR"
                #self.serobject.flushInput()
                #self.serobject.flushOutput()
                self.serobject.write("SOUR1:PULS:TRAN:LEAD %e\n" % trise)
                self.serobject.write("SOUR1:PULS:TRAN:TRA %e\n" % trise)
            else:
                self.serobject.write("PULSE:TRANSITION %f\n" %trise)
    def read_opc(self):
        if self.alive:
            self.set_addr()
            self.serobject.write("*OPC?\n")
            self.serobject.write("++read\n")
            s=self.serobject.readline()
            s=s.strip()
            if s:
                pass
            else:
                self.alive=False
            return s.strip()
    def conf_sweep(self,ioh,iol,d,fmax,fmin,t,v_scale,v_offset):
        if self.alive:
            self.set_addr()
            vh=v_offset+ioh*v_scale
            vl=v_offset+iol*v_scale
            if "TEKTRONIX" in self.instr_name:
                self.serobject.write("OUTP1:IMP 50\n")
                self.serobject.write("OUTP1:POL NORM\n")
                self.serobject.write("SOUR1:AM:STAT OFF\n")
                self.serobject.write("SOUR1:FM:STAT OFF\n")
                self.serobject.write("SOUR1:PM:STAT OFF\n")
                self.serobject.write("SOUR1:PWM:STAT OFF\n")
                self.serobject.write("SOUR1:BURST:STAT OFF\n")
                self.serobject.write("SOUR1:VOLT:UNIT VPP\n")
                self.serobject.write("SOUR1:VOLT:LIM:HIGH 5V\n")
                self.serobject.write("SOUR1:VOLT:LIM:LOW 0V\n")
                self.serobject.write("SOUR1:VOLT:IMM:HIGH %f\n" %vh)
                self.serobject.write("SOUR1:VOLT:IMM:LOW %f\n" %vl)
                self.serobject.write("SOUR1:FUNC:SHAP SQU\n")
                self.serobject.write("SOUR1:FREQ:STAR %e\n" %fmin)
                self.serobject.write("SOUR1:FREQ:STOP %e\n" %fmax)
                self.serobject.write("SOUR1:SWEEP:MODE TIME\n")
                self.serobject.write("SOUR1:SWEEP:TIME %e\n" %t)
                self.serobject.write("SOUR1:SWEEP:RTIME 1ms\n")
                self.serobject.write("SOUR1:SWEEP:HTIME 1ms\n")
                self.serobject.write("SOUR1:SWEEP:SPACING LOG\n")
                self.serobject.write("SOUR1:FREQ:MODE SWEEP\n")
            else:
                self.serobject.write("FUNCTION SQUARE\n")
                self.serobject.write("FUNCTION:SQUARE:DCYCLE %f\n"%d)
                self.serobject.write("VOLTAGE:HIGH %f\n" %vh)
                self.serobject.write("VOLTAGE:LOW %f\n" %vl)
                self.serobject.write("FREQUENCY:START %f\n" %fmin)
                self.serobject.write("FREQUENCY:STOP %f\n" %fmax)
                self.serobject.write("SWEEP:SPACING LIN\n")
                self.serobject.write("SWEEP:STATE ON\n")
                self.serobject.write("SWEEP:TIME %f\n" %t)

def load_find(Load, Fra):
    Load.__init__(addr=Load.addr) # initialise, but keep address as per user definition
    for dev in find_usb_serial_devices():
        if 'Prologix' in dev[1]:
            Load.ifname=dev[0]
            Load.iftype="prologix-gpib"
            if Fra.serobject:
                # check if FRA has already openend interface
                if Fra.serobject.isOpen():
                    # print "...FRA's serial port is already open, let's use it for load ok"
                    Load.serobject=Fra.serobject
            else:
                # FRA hasn't been discovered
                Load.ifclose()
                Load.ifopen()
    Load.set_instr_name()

class Fra(object):
    nof=0
    def __init__(self,namestr="", addr=1):
        Fra.nof+=1
        self.alive=False
        self.instr_name=namestr
        self.instr_version=""
        self.serobject=None
        self.ifname="/dev/tbd"
        self.iftype="tbd"
        self.errors=0
        self.timeout=1
        self.addr=addr
    def __del__(self):
        Fra.nof-=1
    def ifclose(self):
        if self.serobject:
            self.alive=False
            self.serobject.close()
            self.serobject=None
    def ifopen(self):
        # if self.seroject exists, close it and none it
        if self.serobject:
            self.serobject.close()
            self.serobject=None
        try:
            if "prologix-gpib" in self.iftype:
                self.serobject=serial.Serial(self.ifname,timeout=self.timeout)
                # print "debug: self.ifopen() prologix ok"
            elif "rs232" in self.iftype:
                self.serobject=serial.Serial(self.ifname,baudrate=19200, bytesize=8, parity='N', stopbits=1, timeout=self.timeout, xonxoff=0, rtscts=0)
            else:
                self.serobject=None
                self.ifname="/dev/tbd"
                self.iftype="tbd"
        except:
            # problem while opening, clear all if
            self.alive=False
            self.serobject=None
            self.ifname="/dev/tbd"
            self.iftype="tbd"
    def set_addr(self):
        if "prologix-gpib" in self.iftype:
            self.serobject.write("++addr %s\n" % str(self.addr))
            # automatic talk after listen
            self.serobject.write("++auto 1\n")
    def reset(self):
        if "prologix-gpib" in self.iftype:
            # see Prologix spec for explanation. clear sends SDC message to currently addressed device
            # WATCH OUT! using this is known to cause stability problems, FRA no longer responding etc
            self.set_addr()
            self.serobject.write("++clr\n")
    def get_data(self):
        obtained_data=[]
        try:
            if self.alive:
                self.set_addr()
                self.serobject.write("DAV?\n")
                davs=self.serobject.readline().strip()
                if davs:
                    dav=int(davs)
                else:
                    return obtained_data
                if (dav&0x4):
                    self.serobject.write("FRA?SWEEP\n")
                    while True:
                        obtained_line=self.serobject.readline().strip()
                        # print obtained_line
                        if obtained_line=="":
                            break
                        obtained_float_tuple=tuple([float(i) for i in obtained_line.split(",")])
                        # print "obtained data tuple:", obtained_float_tuple
                        obtained_data.append(obtained_float_tuple)
        except KeyboardInterrupt:
            pass
        return obtained_data
    def set_instr_name(self):
        if self.alive:
            self.set_addr()
            self.serobject.write("*IDN?\n")
            s=self.serobject.readline()
            self.instr_name=s.strip()
    def set_instr_version(self):
        if self.alive:
            self.set_addr()
            self.serobject.write("VER?\n")
            s=self.serobject.readline()
            self.instr_version=s.strip()
    def beep(self):
        if self.alive:
            self.set_addr()
            self.serobject.write("BEEP\n")
    def output(self,on="off"):
        if self.alive:
            self.set_addr()
            if "ON" in on.upper():
                self.serobject.write("OUTPUT,ON\n")
            else:
                self.serobject.write("OUTPUT,OFF\n")
    def sweep(self,sweepaction="START"):
        if self.alive:
            self.set_addr()
            if "START" in sweepaction.upper():
                self.serobject.write("START\n")
            else:
                self.serobject.write("STOP\n")
    def sweep_check_completion(self,fstart,fstop):
        if self.alive:
            self.set_addr()
            while True:
                try:
                    self.serobject.write("DAV?\n")
                    davs=self.serobject.readline().strip()
                    if davs:
                        dav=int(davs)
                    else:
                        return -1
                    if (dav&0x4):
                        # full sweep data available, 100% complete
                        return 100.0
                    elif (dav&0x1):
                        self.serobject.write("FRA?\n")
                        fraline=self.serobject.readline().strip()
                        # print "fraline returned", fraline
                        if fraline:
                            freq=float(fraline.split(",")[0])
                            if freq<1e-3:
                                return -1
                            # print "current f=%fkHz" % (freq/1e3)
                            ratio=math.log10(freq/fstart)/math.log10(fstop/fstart)
                            # print "%.1f%% complete" % (ratio*100.0)
                            return min((ratio*100.0),100.0)
                        else:
                            return 100
                except KeyboardInterrupt:
                    # clear input buffer
                    self.serobject.read(1<<10)
                    return -1
        else:
            return -1
    def conf_fr(self,fstatic=2e3,ppd=10,fstart=100,fstop=100e3,speed="medium",
                vinject_lvl=5e-3,vinject_mode='auto_ch1', vinject_tol=40,
                probe_scale_v=10):
        if self.alive:
            self.output("off")
            # *****************************************************
            # general FRA settings
            # *****************************************************
            self.serobject.write("*CLS\n")
            self.serobject.write("FRA\n")
            self.serobject.write("OUTPUT,VOLT\n")
            self.serobject.write("BANDWI,AUTO\n")
            self.serobject.write("FILTER,NORMAL,AUTO\n")
            self.serobject.write("MARKER,OFF\n")
            self.serobject.write("PHCONV,-360\n")
            self.serobject.write("WAVEFO,SINEWA\n")
            # *****************************************************
            # FRA settings relating to output levels and probes
            # *****************************************************
            time.sleep(0.1)
            self.serobject.write("OFFSET,0\n")
            self.serobject.write("COUPLI,CH1,AC+DC\n")
            self.serobject.write("COUPLI,CH2,AC+DC\n")
            self.serobject.write("INPUT,CH1,VOLTAGE\n")
            self.serobject.write("INPUT,CH2,VOLTAGE\n")
            self.serobject.write("INTYPE,CH1,MAIN\n")
            self.serobject.write("INTYPE,CH2,MAIN\n")
            time.sleep(0.1)
            self.serobject.write("RANGE,CH1,AUTO\n")
            self.serobject.write("RANGE,CH2,AUTO\n")
            self.serobject.write("SCALE,CH1,%.2e\n" % probe_scale_v)
            self.serobject.write("SCALE,CH2,%.2e\n" % probe_scale_v)
            if "AUTO" in vinject_mode.upper():
                if "CH2" in vinject_mode.upper():
                    self.serobject.write("ACTRIM,CH2,%.2e,%.1f\n" % (vinject_lvl,vinject_tol))
                else:
                    self.serobject.write("ACTRIM,CH1,%.2e,%.1f\n" % (vinject_lvl,vinject_tol))
            else:
                    self.serobject.write("ACTRIM,DISABL")
            self.serobject.write("AMPLIT,%.2e" % vinject_lvl )
            # *****************************************************
            # FRA settings relating to sweep and data acquisition
            # *****************************************************
            time.sleep(0.1)
            if "SLOW" in speed.upper():
                self.serobject.write("SPEED,SLOW\n")
            elif "FAST" in speed.upper():
                self.serobject.write("SPEED,FAST\n")
            else:
                self.serobject.write("SPEED,MEDIUM\n")
            self.serobject.write("FREQUE,%e\n" % fstatic)
            # determine number of points for sweep
            nof_points=math.ceil(abs((math.log10(fstop)-math.log10(fstart)))*ppd)
            # print "debug: number of sweep points: %f" % nof_points
            self.serobject.write("FSWEEP,%d,%e,%e\n" % (nof_points,fstart,fstop) )
            # *****************************************************
            # FRA settings complete, confirm
            # *****************************************************
            self.serobject.write("BEEP\n")
            # *****************************************************
            # FRA empty read buffer (run into timeout)
            # *****************************************************
            # self.serobject.read(1<<15)

def fra_find(fra):
    fra.__init__(addr=fra.addr) # initialise, but keep address as per user definition
    # prioritise usb-gpib interface ("Prologix")
    for dev in find_usb_serial_devices():
        if 'Prologix' in dev[1]:
            fra_name=fra_find_get_instrument_id(dev[0],"prologix-gpib",fra.addr)
            if fra_name:
                # instrument found, assign basic attributes
                fra.alive=True
                # fra.instr_name=f="tbd/rs232-gpib"
                fra.ifname=dev[0]
                fra.iftype="prologix-gpib"
    # alternatively, look for usb-rs232 interface ("Prolific")
    for dev in find_usb_serial_devices():
        if 'Prolific' in dev[1]:
            fra_name=fra_find_get_instrument_id(dev[0],"rs232",fra.addr)
            if fra_name:
                fra.alive=True
                # fra.instr_name="tbd/rs232"
                fra.ifname=dev[0]
                fra.iftype="rs232"
    # if an instrument was found, permanenlty open it, determine name and version
    if fra.alive:
        fra.ifopen()
        fra.set_instr_name()
        fra.set_instr_version()
        # fra.beep()
    return

def fra_find_get_instrument_id(dev,comms_type,addr=0,timeout=1):
    # just temporarily tries to open comms with a device, get its ID, then close it
    # print "debug: looking at device %s" % dev
    if "prologix-gpib" in comms_type:
        try:
            fra_ser=serial.Serial(dev)
            # clear serial buffer, just read until run into timeout
            fra_ser.timeout=0.1
            s=fra_ser.read(1<<16)
            # print "debug... try to write to %s addr %d, then close" % (dev,addr)
            fra_ser.timeout=timeout
            fra_ser.write("++addr %s\n" % str(addr))
            fra_ser.write("++auto 1\n")
            fra_ser.write("*IDN?\n")
            s=fra_ser.readline()
            s=s.strip()
            # print "debug: *idn? returns %s" % s
            fra_ser.close()
            return s
        except:
            return ""
    if "rs232" in comms_type:
        try:
            fra_ser=serial.Serial(dev,baudrate=19200, bytesize=8, parity='N', stopbits=1, timeout=1, xonxoff=0, rtscts=0)
            # clear serial buffer, just read until run into timeout
            fra_ser.timeout=0.1
            s=fra_ser.read(1<<16)
            # print "debug... try to write to %s addr %d, then close" % (dev,addr)
            fra_ser.timeout=timeout
            fra_ser.write("*IDN?\n")
            s=fra_ser.readline()
            s=s.strip()
            fra_ser.close()
            return s
        except:
            return ""
    else:
        return ""

def find_usb_serial_devices():
    """
    compiles a list of serial USB devices
    """
    devicelist=[]

    if "posix" in os.name:
        # first, look for ttyUSB devices, and filter those supported
        devices=sorted(glob.glob("/dev/ttyUSB*"));
        for device in devices:
            devicelist.append((device,__identify_usb_serial_device(device)))
        # next, look for ttyACM devices, and accept unfiltered (mbed)
        devices=sorted(glob.glob("/dev/ttyACM*"));
        for device in devices:
            devicelist.append((device,"ttyacm"))
        return devicelist

# private functions start here
def __identify_usb_serial_device(fn_dev):
    # example entries in /var/log/syslog
    # Sep 10 14:53:19 kr-w500 kernel: [19700.327218] usb 6-2: pl2303 converter now attached to ttyUSB0
    # Sep 10 14:53:35 kr-w500 kernel: [19716.912596] pl2303 ttyUSB0: pl2303 converter now disconnected from ttyUSB0
    # ACM devices (such as mbed)
    # Sep 10 14:55:48 kr-w500 kernel: [19849.882024] cdc_acm 6-2:1.1: ttyACM0: USB ACM device

    # added Arduino support:
    #Jan  1 11:27:34 kr-w500 kernel: [18923.441170] usb 6-2: Product: Arduino Micro   
    #Jan  1 11:27:34 kr-w500 kernel: [18923.441176] usb 6-2: Manufacturer: Arduino LLC
    #Jan  1 11:27:34 kr-w500 kernel: [18923.444247] cdc_acm 6-2:1.0: ttyACM1: USB ACM device
    id="unknown"
    get_ready_for="unkown"

    logfile="/var/log/syslog"
    dev_tail=os.path.split(fn_dev)[1]
    if os.path.exists(logfile):
        f=open(logfile)
        for line in f:
            if "FT2232H" in line:   # 2-port FTDI dongle
                get_ready_for="FTDI Dongle 2p"
            if "FT4232H" in line:   # 4-port FTDI dongle
                get_ready_for="FTDI Dongle 4p"
            if "FT232RL" in line:
                get_ready_for="Prologix"
            if "pl2303" in line:
                get_ready_for="Prolific"
            if dev_tail in line:
                if "FTDI" in line:
                    if "attached" in line:
                        id=get_ready_for
                    elif "disconn" in line:
                        id="unknown"
                if "pl2303" in line:
                    if "attached" in line:
                        id=get_ready_for
                    elif "disconn" in line:
                        id="unknown"
        f.close()
    return id
