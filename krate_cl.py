#!/usr/bin/python
# KR ATE command line user interface
# history (in reverse order)
# 17/01/2014	smbb hist refinements (optional scaler)
# 04/01/2014    amend Arduino u2i (support ara)
# 03/01/2014    amend Arduino u2i (add smbb stat)
# 02/01/2014    add Arduino u2i mostly supported (except command smbb stat)
# 01/01/2014    add Arduino u2i device support (alternative smbb device)
# 31/12/2013	put under git control (https://github.com/kr64/krate.git)
# 06/08/2013    add stat facility (ambareg statistical word read)
# 05/08/2013    add smbb alpha_clamp facility
# 04/08/2013    add smbb info_dsp facility (overview of dsp registers)
# 22/05/2013    add support for (el-driving) function generator Tektronix AFG3022B
# 18/09/2012    smbb ambareg access (also import register definitions etc)
# 17/09/2012    smbb hal access
# 15/09/2012    smbb vout_command implemented
# 13/11/2011    created

import cmd, os, krate, time, sys, pickle, xlwt, numpy, math

fra1=krate.Fra()
Vin1=krate.Vin()
Load1=krate.Load()
Smbb1=krate.Smbb()

fra_data_index=0
fra_data_dir={}

krate_vars={
    "author": "KR",
    "bp_dbmax": 40.0,
    "bp_dbmin": -20.0,
    "bp_phmax": -100,
    "bp_phmin": -450.0,
    "bp_sizex": 1000,
    "bp_sizey": 1000,
    "dut": "ceb021 f078/d216",
    "fra_sweep_var": "",
    "fra_sweep_value": 0.0,
    "fra_sweep_unit": "",
    "fstatic": 1e3,
    "fstart": 100.0,
    "fstop": 200e3,
    "fsw": 500e3,
    "ph": 2,
    "ppd": 20,
    "vinject_lvl": 5e-3,
    "vinject_mode": "auto_ch1",
    "vinject_tol": 40,
    "speed": "medium",
    "probe_scale_v": 10.0,
    "vi": 12.0,
    "vi_max": 18.0,
    "vi_ilim": 5.0,
    "vi_sweep_start": 6.0,
    "vi_sweep_dir": "up",
    "vi_sweep_min": 6.5,
    "vi_sweep_max": 14.0,
    "vi_sweep_vstep": 0.1,
    "vi_sweep_tstep": 0.02,
    "vo": 1.2,
    "io": 10.0,
    "io_pulse_high": 30.0,
    "io_pulse_low": 10.0,
    "io_pulse_ton": 500e-6,
    "io_pulse_tper": 5e-3,
    "io_pulse_sr": 10,
    "io_sweep_fmin": 1e2,
    "io_sweep_fmax": 1e6,
    "io_sweep_t": 10,
    "io_sweep_d": 33.3,
    "io_burst_count": 10,
    "io_burst_tper": 0.1,
    "of": 5,
    "rdiv": 1.0,
    "alpha": "var",
    "gpib_addr": 23,
    "legend": "",
    "load_gpib_addr": 22,
    "load_v_per_a": 0.015,
    "load_v_offset": 0.00,
    }
krate_gvars={}

hal_addr={
    "alpha": (0x07, 32768),
    "alpha_min": (0x01, 32768),
    "alpha_max": (0x0E, 32768),
    "of_dyn": (0x03, 1),
    "of_stat": (0x04, 1),
    }
registers_amba={}   # empty directory, can be populated through smbb import

valid_shell_commands=("ls","pwd","more","rm")
kratevar_default_fn="krate.var"
kratedata_default_fn="krate.dat"

exit_code=0

class KrateCmd(cmd.Cmd):
    global fra_data_index, fra1, fra_data

    """krate command line interface"""
    def emptyline(self):
        # print 'emptyline()'
        # return cmd.Cmd.emptyline(self)
        pass
    def do_test(self,line):
        # trial area for new test code
        # ACD: repeated startup
        nof_startups=10
	tdur_acd=50e-3
	tdur_acd_rest=2e-3

	received_input=raw_input("REQUEST: Number of ACD startups? (default=%g): "%nof_startups)
        if received_input:
            nof_startups=int(float(received_input))
	received_input=raw_input("REQUEST: ACD duration after Operation ON command (including Trise) (default=%gs): " %tdur_acd)
        if received_input:
            tdur_acd=float(received_input)
	received_input=raw_input("REQUEST: ACD rest after Operation OFF command: (default=%gs): "%tdur_acd_rest)
        if received_input:
            tdur_acd=float(received_input)
	duration_estimated=nof_startups*(tdur_acd+tdur_acd_rest)
	kr_print_message("Info: ACD repeated startup test (%g startups). Estimated duration: %gs" % (nof_startups,duration_estimated) )
	kr_print_message("      Getting ready: Operation OFF. Clear Faults")
	Smbb1.pmbus_operation(0x0)
	time.sleep(tdur_acd_rest)
	Smbb1.pmbus_clear_faults()
	devinfostr=Smbb1.pmbus_devinfo()
	kr_print_message("      Device info: '%s'" % devinfostr )
	v_alpha=list(); v_alphamax=list(); v_alphamin=list();
	for i in xrange(0,nof_startups):
	  Smbb1.pmbus_operation(0x88)
	  time.sleep(tdur_acd)
	  if i==0:
	    # at first turn on, get device telemetry information. Note that FW needs settling time to produce telemetry (give it a second)
	    time.sleep(1.0)
	    devtelestr=Smbb1.pmbus_devtele()
	    kr_print_message("      Telemetry: '%s'" % devtelestr )
	  # just prior to Operation OFF gather alpha information
	  alpha=Smbb1.pmbus_ambareg(0x1847)/32768.0
	  alpha_min=Smbb1.pmbus_ambareg(0x183F)/32768.0
	  alpha_max=Smbb1.pmbus_ambareg(0x1834)/32768.0
	  Smbb1.pmbus_operation(0x0)
	  time.sleep(tdur_acd_rest)
	  Smbb1.pmbus_ara()
	  if len(Smbb1.addr_pmbus_ara):
	    kr_print_message("Error: ACD terminated due to fault" )
	    devinfostr=Smbb1.pmbus_devinfo()
	    kr_print_message("       Device info: '%s'" % devinfostr )
	    break;
	  # if no faults, append alpha values to lists
	  v_alpha.append(alpha); v_alphamax.append(alpha_max); v_alphamin.append(alpha_min); 
	  kr_print_message("      Startup %g: alpha=%g alpha_min=%g alpha_max=%g" % (i,alpha,alpha_min,alpha_max) )
 	kr_print_message("Info: ACD tests complete. Recorded alpha values: %.0f" %len(v_alpha) )
 	if len(v_alpha)>0:
	  kr_write_smbbreg("acd_alpha",v_alpha)
	  kr_write_smbbreg("acd_alphamax",v_alphamax)
	  kr_write_smbbreg("acd_alphamin",v_alphamin)
	  statstr="Samples=%.0f Min=%g Max=%g Pkpk=%0g Mean=%.3f Stdev=%.3f" % (len(v_alpha),min(v_alpha),max(v_alpha),(max(v_alpha)-min(v_alpha)),numpy.mean(v_alpha),numpy.std(v_alpha))
	  kr_write_gnuplot_hist("acd_alpha", v_alpha, "ACD %.0f startups: alpha (dsp_y7) q0.15"%nof_startups, devinfostr, devtelestr, statstr, True, "blue")
	  statstr="Samples=%.0f Min=%g Max=%g Pkpk=%0g Mean=%.3f Stdev=%.3f" % (len(v_alphamax),min(v_alphamax),max(v_alphamax),(max(v_alphamax)-min(v_alphamax)),numpy.mean(v_alphamax),numpy.std(v_alphamax))
	  kr_write_gnuplot_hist("acd_alphamax", v_alphamax, "ACD %.0f startups: alpha_max (dsp_x20) q0.15"%nof_startups, devinfostr, devtelestr, statstr, False, "red")
	  statstr="Samples=%.0f Min=%g Max=%g Pkpk=%0g Mean=%.3f Stdev=%.3f" % (len(v_alphamin),min(v_alphamin),max(v_alphamin),(max(v_alphamin)-min(v_alphamin)),numpy.mean(v_alphamin),numpy.std(v_alphamin))
	  kr_write_gnuplot_hist("acd_alphamin", v_alphamin, "ACD %.0f startups: alpha_min (dsp_x31) q0.15"%nof_startups, devinfostr, devtelestr, statstr, False, "green")

    def do_smbb(self,line):
        """ interact with SMBus Bridge (smbb)
  'smbb addr' sets the active address for smbus transactions
  'smbb ara' makes ARA (address resolution protocol) enquiries
  'smbb alpha_clamp' sets alpha_min and alpha_max
  'smbb ambareg {reg[=value]}' reads from, or writes value to, device amba register
  'smbb clear_faults' clears PMBus faults status register
  'smbb frequency_switch fsw' sets switching frequency to fsw (375-1000kHz in 125kHz steps
  'smbb hal reg [value]' reads from, or writes value to, device HAL register
  'smbb hist[u] reg [nof] [scaler]' reads amba register [u]=unsigned nof times scaled then histogram
  'smbb import reg fn' imports amba register definitions from assembly list file
  'smbb info' obtains basic device information from active smbus device
  'smbb info_dsp' provides overview of dsp registers
  'smbb tele' obtains basic device telemetry information from active smbus device
  'smbb find' attempts to detect available smbb device
  'smbb operation {on|off}' sends PMBus OPERATION command to smbus device
  'smbb scan' scans smbus for available devices, and activates lowest address
  'smbb stat reg [nof]' statistical word read of an ambareg register (producing min/max/avg)
  'smbb telemetry' obtains basic device telemetry information from active smbus device
  'smbb vout_command vo' sets a new output voltage"""
	Smbb1.ifflush()		# discard all data in serial input and output buffer
        if (len(line.split())>0):
            if "find" in (line.split()[0]):
                krate.smbb_find(Smbb1)
                kr_list_smbb()
            elif "scan" in (line.split()[0]):
                Smbb1.scan_pmbus_addresses()
		Smbb1.pmbus_address_set()
		Smbb1.pmbus_ara()
                kr_list_smbb()
            elif "ara" in (line.split()[0]):
		Smbb1.pmbus_ara()
		kr_list_smbb()
            elif "addr" in (line.split()[0]):
                if len(line.split())>1:
                    Smbb1.addr_pmbus_active=int(line.split()[1])
                    Smbb1.pmbus_address_set()
                    kr_list_smbb()
                else:
                    kr_print_message("Error: smbb addr expects an argument")
            elif "alpha" in (line.split()[0]):
                nof_args=len(line.split())
                if nof_args==2:
                    alpha_min=float(line.split()[1])
                    alpha_max=alpha_min
                elif nof_args==3:
                    alpha_min=float(line.split()[1])
                    alpha_max=float(line.split()[2])
                else:
                    kr_print_message("Error: smbb alpha expects one or two arguments")
                if ((nof_args==2) | (nof_args==3)):
                    if ( (alpha_min>=0.0) & (alpha_min<=1.0) & (alpha_max>=0.0) & (alpha_max<=1.0) ):
                        alpha_min_q015=alpha_min*(1<<15)
                        if alpha_min_q015>((1<<15)-1): alpha_min_q015=((1<<15)-1)
                        alpha_max_q015=alpha_max*(1<<15)
                        if alpha_max_q015>((1<<15)-1): alpha_max_q015=((1<<15)-1)
                        Smbb1.pmbus_ambareg(0x183F,int(alpha_min_q015))
                        Smbb1.pmbus_ambareg(0x1834,int(alpha_max_q015))
                        alpha=Smbb1.pmbus_ambareg(0x1847)
                        kr_print_message("INFO: Write alpha_min=%0.3f alpha_max=%0.3f. Read alpha=%0.3f" % (alpha_min,alpha_max,alpha/32768.0) )
                    else:
                        kr_print_message("Error: argument outside range [0.0..1.0]")
            elif "info_dsp" in (line.split()[0]):
	      try:
                devinfostr=Smbb1.pmbus_devinfo()
                dspstr=Smbb1.pmbus_read_dsp_version()
                kr_print_message("INFO: DSP '%s' Overview" % dspstr )
                alpha=Smbb1.pmbus_ambareg(0x1847)
                alpha_min=Smbb1.pmbus_ambareg(0x183F)
                alpha_max=Smbb1.pmbus_ambareg(0x1834)
                wa4=Smbb1.pmbus_ambareg(0x1829)
                prbs_coefficient=Smbb1.pmbus_ambareg(0x1824)
                sariu_inv_vin=Smbb1.pmbus_ambareg(0x281B)
                bd1=Smbb1.pmbus_ambareg(0x1820)
                b01=Smbb1.pmbus_ambareg(0x1821)
                a1_taux=Smbb1.pmbus_ambareg(0x1825)
                kd0=Smbb1.pmbus_ambareg(0x1826)
                k00=Smbb1.pmbus_ambareg(0x1827)
                ki=Smbb1.pmbus_ambareg(0x184c)
                kr_print_message("      alpha(y7)=%0.3f alpha_min(x31)=%0.3f alpha_max(x20)=%0.3f" % (alpha/32768.0,alpha_min/32768.0,alpha_max/32768.0) )
                kr_print_message("      AZ: wa/4(x9)=%0.3f which should be reasonably close to sariu_inv_vin(z9)=%0.3f" % (wa4/32768.0,sariu_inv_vin/32768.0) )
                kr_print_message("      Compensator: x0=0x%04x x1=0x%04x x5=0x%04x x6=0x%04x x7=0x%04x y12=0x%04x" % (bd1,b01,a1_taux,kd0,k00,ki) )
                kr_print_message("      PRBS noise coefficient(x4)=0x%04x=%.3e(q0.15)" % (prbs_coefficient,prbs_coefficient/32768.0) )
	      except:
		kr_print_message("Error: smbb communication problems")
            elif "info" in (line.split()[0]):
	      try:
                devinfostr=Smbb1.pmbus_devinfo()
                kr_print_message("INFO: %s" % devinfostr )
	      except:
		kr_print_message("Error: smbb communication problems")
            elif "tele" in (line.split()[0]):
	      try:
                devtelestr=Smbb1.pmbus_devtele()
                kr_print_message("INFO: %s" % devtelestr )
	      except:
		kr_print_message("Error: smbb communication problems")
            elif "clear_faults" in (line.split()[0]):
                Smbb1.pmbus_clear_faults()
                devinfostr=Smbb1.pmbus_devinfo()
                kr_print_message("INFO: %s" % devinfostr )
            elif "operation" in (line.split()[0]):
                if len(line.split())>1:
                    if "on" in line.split()[1].lower():
                        Smbb1.pmbus_operation(0x88)
                    elif "off" in line.split()[1].lower():
                        Smbb1.pmbus_operation(0x0)
                    else:
                        kr_print_message("Error: wrong argument '%s'" % line.split()[1])
                else:
                    kr_print_message("Error: smbb operation expects an argument")
            elif "vout_command" in (line.split()[0]):
                if len(line.split())>1:
                    try:
                        vo=float(line.split()[1])
                        if vo>=0.1 and vo<=5.6:
                            Smbb1.pmbus_vout_command(vo)
                        else:
                            kr_print_message("Error: argument outside range")
                    except:
                        kr_print_message("Error: smbb vout_command expects an argument")
                else:
                    kr_print_message("Error: smbb vout_command expects an argument")
            elif "hal" in (line.split()[0]):
                if len(line.split())>1:
                    hal_n=line.split()[1]
                else:
                    hal_n=""
                if "=" in hal_n:
                    (hal_n,hal_v)=hal_n.split("=")
                    if hal_n in hal_addr.keys():
                        hal_v=eval(hal_v)
                        (hal_a,hal_m)=hal_addr[hal_n]
                        # print hal_a, hal_m, hal_v
                        kr_print_message("INFO: hal register %d=0x%04x" % (hal_a,int(hal_v*hal_m)))
                        Smbb1.pmbus_hal(hal_a,int(hal_v*hal_m))
                    else:
                        kr_print_message("Error: hal register '%s' not known" %hal_n )
                else:
                    for i in sorted(hal_addr.keys()):
                        if hal_n in i:
                            (hal_a,hal_m)=hal_addr[i]
                            if hal_m==1:
                                kr_print_message("INFO: hal register %s=0x%04x" % (i,Smbb1.pmbus_hal(hal_a)))
                            else:
                                kr_print_message("INFO: hal register %s=%.3f" % (i,float(Smbb1.pmbus_hal(hal_a)/float(hal_m))))
                            if hal_n==i:
                                # exact hal name match, assume stop
                                break
            elif "amba" in (line.split()[0]):
                if len(line.split())>1:
                    ambareg_n=line.split()[1]
                else:
                    ambareg_n="name not defined"
                if "=" in ambareg_n:
                    (ambareg_n,ambareg_v)=ambareg_n.split("=")
                    if ambareg_n in registers_amba.keys():
                        ambareg_v=eval(ambareg_v)
                        ambareg_a=registers_amba[ambareg_n]
                        kr_print_message("INFO: register [0x%04X]=0x%04x" % (ambareg_a,int(ambareg_v)))
                        Smbb1.pmbus_ambareg(ambareg_a,int(ambareg_v))
                    else:
                        kr_print_message("Error: register '%s' not known" %ambareg_n )
                else:
                    for i in sorted(registers_amba.keys()):
                        if ambareg_n in i:
                            ambareg_a=registers_amba[i]
                            ambareg_v=Smbb1.pmbus_ambareg(ambareg_a)
                            if ambareg_v!=None:
			      kr_print_message("INFO: register %s [0x%04X] reads 0x%04x" % (i,ambareg_a,ambareg_v))
			    else:
			      kr_print_message("ERROR: failed to read register %s [0x%04X]" % (i,ambareg_a))
            elif "hist" in (line.split()[0]):
		if "histu" in (line.split()[0]):
		  treat_values_unsigned=True
		else:
		  treat_values_unsigned=False
                register_found=False
                if len(line.split())>1:
                    ambareg_n=line.split()[1]
                else:
                    ambareg_n=None
                if len(line.split())>2:
                    nof_reads=float(line.split()[2])
                else:
                    nof_reads=1000.0
                if nof_reads<0:
                    nof_reads=nof_reads*-1;
                nof_reads=int(nof_reads)
                if len(line.split())>3:
                    scaler=eval(line.split()[3])
                else:
                    scaler=1.0
                if ambareg_n:
                    for i in sorted(registers_amba.keys()):
                        if ambareg_n==i:
                            register_found=True
                            ambareg_a=registers_amba[ambareg_n]
                            duration_estimated=nof_reads*(5.0*10.0*(1/400e3)+2e-3)	# raw read duration: S+addr/w+cmd+Sr+addr/r+lsb+msb, plus usb/python overhead say 100%
                            kr_print_message("Info: Histogram register %s (0x%04x) scaled by %.1e based on %.0f values. Estimated duration: %.1fs" % (ambareg_n,ambareg_a,scaler,float(nof_reads),duration_estimated) )
                            ambareg_v=Smbb1.pmbus_ambareg_nof(ambareg_a,nof_reads,scaler,treat_values_unsigned)	# read ambareg_a nof_reads times, treat values signed/unsigned
                            if ambareg_v:
			      reginfostr="%s (addr 0x%04x)" % (ambareg_n,ambareg_a)
			      if scaler<>1:
				reginfostr=reginfostr+" scaled by %g" % scaler
			      devinfostr=Smbb1.pmbus_devinfo()
			      devtelestr=Smbb1.pmbus_devtele()
			      statstr="Samples=%.0f Min=%g Max=%g Pkpk=%0g Mean=%.3f Stdev=%.3f" % (len(ambareg_v),min(ambareg_v),max(ambareg_v),(max(ambareg_v)-min(ambareg_v)),numpy.mean(ambareg_v),numpy.std(ambareg_v))
			      kr_print_message("Info: Stats:     %s" % (statstr))
			      kr_print_message("      Register   %s" % (reginfostr))
			      kr_print_message("      Device:    %s" % (devinfostr))
			      kr_print_message("      Telemetry: %s" % (devtelestr))
			      kr_write_smbbreg("smbbambareg",ambareg_v)
			      kr_write_gnuplot_hist("smbbambareg", ambareg_v, reginfostr, devinfostr, devtelestr, statstr, True)
                    if register_found==False:
                        kr_print_message("Error: Unknown register '%s' (need a fully qualified name. try list reg xxx)" % ambareg_n )
                else:
                    kr_print_message("Error: smbb hist expects at least one argument (register name)" )
            elif "stat" in (line.split()[0]):
                # we're expecting 1 or 2 arguments. which register, and number of reads (if not given, 1k default)
                register_found=False
                if len(line.split())>1:
                    ambareg_n=line.split()[1]
                else:
                    ambareg_n=None
                if len(line.split())>2:
                    nof_reads=float(line.split()[2])
                else:
                    nof_reads=1000.0
                if nof_reads<0:
                    nof_reads=nof_reads*-1;
                if ambareg_n:
                    for i in sorted(registers_amba.keys()):
                        if ambareg_n==i:
                            ambareg_a=registers_amba[ambareg_n]
                            duration_estimated=nof_reads*5.0*10.0*(1/400e3)
                            kr_print_message("Info: Statistical read of register %s (0x%04x) %.0f times. Estimated duration: %.1fs" % (ambareg_n,ambareg_a,float(nof_reads),duration_estimated) )
                            register_found=True
                            stats=Smbb1.statr2(ambareg_a,nof_reads,duration_estimated*10)
                            if stats:
                                kr_print_message("      Answer: min=%d=0x%04x max=%d=0x%04x pkpk=%dlsb avg=%.3f=%.3f(q0.15)" % (stats[0],stats[0],stats[1],stats[1],stats[1]-stats[0],stats[2],stats[2]/(1<<15)) )
                            else:
                                kr_print_message("      Answer: None")
                            break
                    if register_found==False:
                        kr_print_message("Error: Unknown register '%s' (need a fully qualified name. try list reg xxx)" % ambareg_n )
                else:
                    kr_print_message("Error: smbb stat expects at least one argument (register name)" )
            elif "import" in (line.split()[0]):
                if len(line.split())<2:
                    kr_print_message("Error: smbb import expects more arguments")
                else:
                    if len(line.split())==2:
                        fn="3012_FW.LST"
                    else:
                        fn=line.split()[2]
                    if "reg" in line.split()[1]:
                        kr_import_register_definitions(fn)
                    else:
                        kr_print_message("Error: don't know what to import" )
            elif "frequency" in (line.split()[0]):
                if len(line.split())<2:
                    kr_print_message("Error: smbb frequency_switch expects more arguments")
                else:
                    try:
                        fsw=eval(line.split()[1])
                        if fsw>=250e3:
                            fsw=fsw/1e3
                        if fsw<250 or fsw>1000:
                            kr_print_message("Error: dodgy parameter")
                        else:
                            fsw125=int(fsw/125)*125
                            Smbb1.pmbus_frequency_switch(fsw)
                    except:
                        kr_print_message("Error: dodgy parameter")
            elif "phases" in (line.split()[0]):
                if len(line.split())<2:
                    # gs=Smbb1.pmbus_general_settings()
                    # kr_print_message("Debug: General settings=0x%04x" % gs)
                    nof_phases=Smbb1.pmbus_phases()
                    kr_print_message("Info: Read phases=%d" % nof_phases)
                else:
                    try:
                        ph=int(eval(line.split()[1]))
                        if ph<1 or ph>2:
                            kr_print_message("Error: dodgy parameter")
                        else:
                            Smbb1.pmbus_phases(ph)
                    except:
                        kr_print_message("Error: dodgy parameter")
            else:
                kr_print_message("Error: don't know what to do with %s" %line.split()[0] )
        else:
            kr_print_message("Error: smbb command expects an argument")
    def complete_smbb(self, text, line, begidx, endidx):
        LIST_ITEMS = ['ara','addr','alpha_clamp','ambareg','clear_faults','find','frequency_switch','hal','hist','histu','import','info','info_dsp','operation','phases','scan','stat','telemetry','vout_command']
        if not text:
            completions = LIST_ITEMS[:]
        else:
            completions = [ f
                            for f in LIST_ITEMS
                            if f.startswith(text)
                            ]
        return completions

    def do_vin(self,line):
        """  {arg} interact with Frequency Response Analyser
  'vin conf' configures Vin supply
  'vin find' attempts to detect available Vin device
  'vin off' disables output of Vin supply
  'vin on' enables output of Vin supply"""
        if (len(line.split())>0):
            if "find" in (line.split()[0]):
                krate.vin_find(Vin1,fra1)
                kr_list_vin()
                if Vin1.alive:
                    Vin1.remote_off()
                    time.sleep(0.1)
                    Vin1.remote_on()
            elif "conf" in (line.split()[0]):
                if Vin1.alive:
                    Vin1.conf(vo=krate_vars['vi'],vomax=krate_vars['vi_max'],iomax=krate_vars['vi_ilim'])
                if Vin1.alive:
                    kr_print_message("INFO: Configured Vin for vin=%.1fV vin_max=%.1fV vin_ilim=%.1fA" %
                        (krate_vars['vi'],krate_vars['vi_max'],krate_vars['vi_ilim']))
            elif "on" in (line.split()[0]):
                if Vin1.alive:
                    Vin1.output(1)
                if Vin1.alive:
                    kr_print_message("INFO: Vin is now ON")
            elif "off" in (line.split()[0]):
                if Vin1.alive:
                    Vin1.output(0)
                if Vin1.alive:
                    kr_print_message("INFO: Vin is now OFF")
            else:
                kr_print_message("Error: don't know what to do with %s" %line.split()[0] )
        else:
            kr_print_message("Error: vin command expects an argument")
    def complete_vin(self, text, line, begidx, endidx):
        LIST_ITEMS = ['find','conf','on','off']
        if not text:
            completions = LIST_ITEMS[:]
        else:
            completions = [ f
                            for f in LIST_ITEMS
                            if f.startswith(text)
                            ]
        return completions

    def do_el(self,line):
        """ el {arg} interact with electronic load
  'el burst' configures electronic load for burst mode
  'el conf' configures electronic load
  'el find' attempts to detect available electronic load device
  'el off' disables electronic load
  'el on' enables electronic load
  'el pulse' configures electronic load device for static operation
  'el static' configures electronic load device for static operation
  'el sweep' configures electronic load device for frequency sweep operation"""
        if (len(line.split())>0):
            if "find" in (line.split()[0]):
                Load1.addr=krate_vars['load_gpib_addr']
                krate.load_find(Load1,fra1)
                kr_list_load()
            if "on" in (line.split()[0]):
                if Load1.alive:
                    Load1.output("on")
            if "off" in (line.split()[0]):
                if Load1.alive:
                    Load1.output("off")
            if "static" in (line.split()[0]):
                if Load1.alive:
                    kr_print_message("Info: Set static current to io=%0.1fA" % krate_vars["io"])
                    Load1.conf_static(krate_vars["io"],krate_vars["load_v_per_a"],krate_vars["load_v_offset"])
            if "burst" in (line.split()[0]):
                # first of all, re-configure pulse (just in case we were in a non-pulse mode)
                if Load1.alive:
                    io_ph=krate_vars["io_pulse_high"]
                    io_pl=krate_vars["io_pulse_low"]
                    io_ton=krate_vars["io_pulse_ton"]
                    io_tper=krate_vars["io_pulse_tper"]
                    io_sr=krate_vars["io_pulse_sr"]
                    io_bcount=krate_vars["io_burst_count"]
                    io_bper=krate_vars["io_burst_tper"]
                    io_Tr=(io_ph-io_pl)/(io_sr/1e-6)
                    io_BW=0.35/io_Tr
                    kr_print_message("Info: Set pulse: %0.1fA..%0.1fA @ %0.1fA/us, Ton=%0.2fms Tper=%0.2fms (equ BW=%.0fkHz)"
                         % (io_pl,io_ph,io_sr,io_ton*1e3,io_tper*1e3,io_BW/1e3))
                    kr_print_message("      Set burst: count=%d, period=%0.1fms"
                         % (io_bcount,io_bper/1e-3))
                    Load1.conf_pulse(io_ph,io_pl,io_ton,io_tper,io_sr,krate_vars["load_v_per_a"],krate_vars["load_v_offset"])
                    Load1.conf_burst(io_bcount,io_bper)
            if "pulse" in (line.split()[0]):
                if Load1.alive:
                    io_ph=krate_vars["io_pulse_high"]
                    io_pl=krate_vars["io_pulse_low"]
                    io_ton=krate_vars["io_pulse_ton"]
                    io_tper=krate_vars["io_pulse_tper"]
                    io_sr=krate_vars["io_pulse_sr"]
                    io_Tr=(io_ph-io_pl)/(io_sr/1e-6)
                    io_BW=0.35/io_Tr
                    kr_print_message("Info: Set pulse current: %0.1fA..%0.1fA @ %0.1fA/us, Ton=%0.2fms Tper=%0.2fms (equ BW=%.0fkHz)"
                         % (io_pl,io_ph,io_sr,io_ton*1e3,io_tper*1e3,io_BW/1e3))
                    Load1.conf_pulse(io_ph,io_pl,io_ton,io_tper,io_sr,krate_vars["load_v_per_a"],krate_vars["load_v_offset"])
            if "sweep" in (line.split()[0]):
                if Load1.alive:
                    io_ph=krate_vars["io_pulse_high"]
                    io_pl=krate_vars["io_pulse_low"]
                    io_fmin=krate_vars["io_sweep_fmin"]
                    io_fmax=krate_vars["io_sweep_fmax"]
                    io_t=krate_vars["io_sweep_t"]
                    io_d=krate_vars["io_sweep_d"]   # d not supported by some function generators (e.g. Tektronix AFB3022)
                    if "TEKTRONIX" in Load1.instr_name:
                        kr_print_message("Info: Set square sweep load: %0.1fA..%0.1fA covering %0.1f..%0.1fkHz in %.1fs"
                            % (io_pl,io_ph,io_fmin/1e3,io_fmax/1e3,io_t))
                    else:
                        kr_print_message("Info: Set rect sweep load: %0.1fA..%0.1fA d=%.1f%% covering %0.1f..%0.1fkHz in %.1fs"
                            % (io_pl,io_ph,io_d,io_fmin/1e3,io_fmax/1e3,io_t))
                    Load1.conf_sweep(io_ph,io_pl,io_d,io_fmax,io_fmin,io_t,krate_vars["load_v_per_a"],krate_vars["load_v_offset"])
        else:
            kr_print_message("Error: el command expects an argument")
    def complete_el(self, text, line, begidx, endidx):
        LIST_ITEMS = ['find','on','off','static','pulse','burst','sweep']
        if not text:
            completions = LIST_ITEMS[:]
        else:
            completions = [ f
                            for f in LIST_ITEMS
                            if f.startswith(text)
                            ]
        return completions

    def do_fra(self,line):
        """ fra {arg} interact with Frequency Response Analyser
  'fra conf' configures FRA for FR measurement
  'fra find' attempts to detect available FRA device
  'fra get' collects data from FRA device
  'fra import' imports FRA data from file (data generated by Scilab or similar)
  'fra output {on|off}' turns output of FRA on or off
  'fra start' starts FR sweep
  'fra stop' stops FR sweep
  'fra wait' waits for FR sweep to complete"""

        if (len(line.split())>0):
            if "find" in (line.split()[0]):
                fra1.addr=krate_vars['gpib_addr']
                krate.fra_find(fra1)
                kr_list_fra()
##            elif "reset" in (line.split()[0]):
##                kr_print_message("INFO: SDC message sent to FRA")
##                fra1.reset()
            elif "start" in (line.split()[0]):
                fra1.output("on")
                fra1.sweep("start")
            elif "stop" in (line.split()[0]):
                fra1.sweep("stop")
            elif "get" in (line.split()[0]):
                kr_fra_get()
            elif "import" in (line.split()[0]):
                # check if file name is provided
                if len(line.split())>1:
                    kr_fra_import(line.split()[1])
                else:
                    kr_print_message("Error: Please provide a file name for import")
            elif "wait" in (line.split()[0]):
                kr_fra_wait()
            elif "output" in (line.split()[0]):
                if len(line.split())>1:
                    fra1.output(line.split()[1])
                else:
                    kr_print_message("Error: fra output expects an argument")
            elif "conf" in (line.split()[0]):
                if len(line.split())>1:
                    pass
                else:
                    # configure for FRA if no arguments provided
                    fra1.conf_fr(
                        fstatic=krate_vars['fstatic'],
                        ppd=krate_vars['ppd'],
                        fstart=krate_vars['fstart'],
                        fstop=krate_vars['fstop'],
                        speed=krate_vars['speed'],
                        vinject_lvl=krate_vars['vinject_lvl'],
                        vinject_mode=krate_vars['vinject_mode'],
                        vinject_tol=krate_vars['vinject_tol'],
                        probe_scale_v=krate_vars['probe_scale_v'],
                        
                        )
                    if fra1.alive:
                        kr_print_message("INFO: Configured FRA (Gain/Phase Measurement)")
                        kr_print_message("      fstatic=%.0fHz, fstart=%.0fHz, fstop=%.0fHz, ppd=%d, speed='%s'" %
                                         (krate_vars['fstatic'],krate_vars['fstart'],krate_vars['fstop'],krate_vars['ppd'],krate_vars['speed']))
                        kr_print_message("      vinject_mode='%s', vinject_lvl=%.1fmV, vinject_tol=%.1f%%" %
                                         (krate_vars['vinject_mode'],krate_vars['vinject_lvl']*1e3,krate_vars['vinject_tol']))
                        kr_print_message("      probe_scale_v=%.1f" %
                                         (krate_vars['probe_scale_v']))
            else:
                kr_print_message("Error: dodgy fra argument")
        else:
            kr_print_message("Error: fra command expects an argument")

    def complete_fra(self, text, line, begidx, endidx):
        LIST_ITEMS = ['find','output','conf','start','stop','wait','get','import']
        if not text:
            completions = LIST_ITEMS[:]
        else:
            completions = [ f
                            for f in LIST_ITEMS
                            if f.startswith(text)
                            ]
        return completions

    def do_ver(self, line):
        """ displays software version information"""
        kr_print_message("INFO: %s" % krate.krate_version())
    def do_clear(self, line):
        """ clears command window"""
        os.system("clear")
    def do_exit(self, line):
        """ exits program"""
        kr_print_message("INFO: Thanks for using krate")
        return True
    def do_run(self, line):
        """ 'run fn' executes a custom test program"""
        if (len(line.split())>0):
            if os.path.exists(line.split()[0]):
##                try:
                    f=open(line.split()[0],"rt")
                    s=f.read(1<<16)
                    f.close()
                    exec(s)
##                except:
##                    kr_print_message("Error: Syntax in '%s'" % line.split()[0])
            else:
                kr_print_message("Error: Can't find '%s'" % line.split()[0])
        else:
            kr_print_message("Error: run expects an filename")
    def do_bodepm(self, line):
        """ 'bodepm' produces pm/fc summary plot(s) for FRA data set(s)"""
        # collect sweep variable information
        sweep_vars=set()
        keys=sorted(fra_data_dir.keys(),key=int)
        for idx in keys:
            if fra_data_dir[idx].sweep_var!="":
                sweep_vars.add(fra_data_dir[idx].sweep_var)
                sweep_unit=fra_data_dir[idx].sweep_unit
                dutstr=fra_data_dir[idx].dut+"/"+fra_data_dir[idx].author+"/"+fra_data_dir[idx].frasetup
        if len(sweep_vars)>0:
            for sweep_var in sweep_vars:
                kr_write_pmfc(fn="frasweep_%s.tmp" % sweep_var, var=sweep_var)
                kr_write_gnuplot_pmfc(fn="kratesweep_%s.gp" % sweep_var,fn_data="frasweep_%s.tmp" % sweep_var, xvar=sweep_var,xunit=sweep_unit,dut=dutstr,exe_gnuplot=True)

    def do_bode(self, line):
        """ 'bode [index1 index2 ...]' produces bode plot(s) for FRA data set(s)"""
        keys=sorted(fra_data_dir.keys(),key=int)
        fra_indices=[]
        if (len(line.split())>0):
            for idx in line.split():
                if idx in keys:
                    fra_indices.append(idx)
                else:
                    kr_print_message("Warning: FRA data set '%s' does not exist" % idx)
        else:
            fra_indices=keys
        c=""
        print "fra_indices: ",fra_indices
        if len(fra_indices)>1: c="s"
        for idx in fra_indices:
            kr_show_info_fra(idx)
            kr_write_fra(idx,fn="fra_%s.tmp" % idx,overwrite=True,ph_adjust=True)
        if len(fra_indices)>0:
            kr_write_gnuplot(fra_indices,fn="krate.gp",exe_gnuplot=True)

    def do_parrot(self, line):
        """ debug only. echoes command line entered, without command itself"""
        kr_print_message("INFO: Thanks for entering '%s'" % line)

    def do_del(self,line):
        """ del item deletes information
  'del data' deletes all FRA data sets
  'del data n' selectively deletes FRA data set(s) n ..."""
        if (len(line.split())>0):
            if "dat" in (line.split()[0]):
                keys=sorted(fra_data_dir.keys(),key=int)
                fra_indices=[]
                if len(line.split())==1:
                    fra_indices=keys
                else:
                    for idx in line.split():
                        if "dat" in idx:
                            pass
                        elif idx in keys:
                            fra_indices.append(idx)
                        else:
                            kr_print_message("Warning: FRA data set '%s' does not exist" % idx)
                if len(fra_indices)>0:
                    for i in fra_indices:
                        kr_print_message("Info: Deleting data set %s" % str(i))
                        del fra_data_dir[i]
                    # krcmd.prompt="krate(%d)> " % len(fra_data_dir)
                if len(fra_data_dir)>0:
                    # identify highest index
                    fra_data_index=max(int(i) for i in fra_data_dir.keys())+1
                else:
                    fra_data_index=0
                krcmd.prompt="krate(i=%d/c=%d)> " % (fra_data_index,len(fra_data_dir))
            else:
                kr_print_message("Error: Don't know what to delete")
        else:
            kr_print_message("Error: del expects arguments")
    def complete_del(self, text, line, begidx, endidx):
        LIST_ITEMS = [ 'data' ]
        if not text:
            completions = LIST_ITEMS[:]
        else:
            completions = [ f
                            for f in LIST_ITEMS
                            if f.startswith(text)
                            ]
        return completions

    def do_list(self,line):
        """ list [item] provides information
  'list comm' lists available device communication ports
  'list data' lists collected FR data
  'list el'   lists electronic load instrument
  'list fra'  lists available FRA instrument
  'list hal'  lists defined HAL addresses
  'list reg'  lists defined registers
  'list smbb' lists available SMBus bridge devices
  'list usb'  lists available device communication ports
  'list var'  lists defined variables
  'list vin'  lists available Vin instrument"""
        if (len(line.split())>0):
            if "dat" in (line.split()[0]):
                kr_list_data()
            if "var" in (line.split()[0]):
                if len(line.split())>1:
                    kr_list_vars(krate_vars, pattern=line.split()[1])
                else:
                    kr_list_vars(krate_vars)
            if "comm" in (line.split()[0]):
                kr_list_serial_devices()
            if "dev" in (line.split()[0]):
                kr_list_serial_devices()
            if "usb" in (line.split()[0]):
                kr_list_serial_devices()
            if "fra" in (line.split()[0]):
                kr_list_fra()
            if "vin" in (line.split()[0]):
                kr_list_vin()
            if "el" in (line.split()[0]):
                kr_list_load()
            if "hal" in (line.split()[0]):
                kr_list_hal()
            if "reg" in (line.split()[0]):
                if len(line.split())>1:
                    kr_list_reg(pattern=line.split()[1])
                else:
                    kr_list_reg()
            if "smbb" in (line.split()[0]):
                kr_list_smbb()
        else:
            # list everything worthwhile listing...
            kr_list_vars(krate_vars)
            kr_list_serial_devices()
            kr_list_fra()
            kr_list_vin()
            kr_list_load()
            kr_list_smbb()
    def complete_list(self, text, line, begidx, endidx):
        LIST_ITEMS = [ 'var', 'comm', 'usb', 'dev', 'fra', 'data', 'vin','el','hal','reg' ]
        if not text:
            completions = LIST_ITEMS[:]
        else:
            completions = [ f
                            for f in LIST_ITEMS
                            if f.startswith(text)
                            ]
        return completions

    def do_save(self,line):
        """ save var [fn] saves defined variables (default fn='krate.var')
 save dat [fn] saves FRA data (default fn='krate.dat')
 save dat fn.xls exports FRA data in spreadsheet/worksheet format"""
        if (len(line.split())>0):
            savewhat=line.split()[0].upper()
            if "DAT" in savewhat:
                if len(line.split())>1:
                    # check if xls file is to be generated
                    if ".XLS" in line.split()[1].upper():
                        kr_export_data(line.split()[1],fra_data_dir,overwrite=True)
                    else:
                        kr_save_data(line.split()[1],fra_data_dir,overwrite=True)
                else:
                    kr_save_data(kratedata_default_fn,fra_data_dir,overwrite=True)
            elif "VAR" in savewhat:
                if len(line.split())>1:
                    kr_save_vars(line.split()[1],krate_vars,overwrite=True)
                else:
                    kr_save_vars(kratevar_default_fn,krate_vars,overwrite=True)
            else:
                kr_print_message("Error: Cannot save '%s'" % savewhat)
        else:
            kr_print_message("Error: save command expects at least one argument")
    def complete_save(self, text, line, begidx, endidx):
        LIST_ITEMS = [ 'var', 'data']
        if not text:
            completions = LIST_ITEMS[:]
        else:
            completions = [ f
                            for f in LIST_ITEMS
                            if f.startswith(text)
                            ]
        return completions

    def do_load(self,line):
        """ load var [fn] loads variables (default fn='krate.var')
 load dat [fn] loads previously saved FRA data  (default fn='krate.dat')"""
        if (len(line.split())>0):
            loadwhat=line.split()[0].upper()
            if "DAT" in loadwhat:
                if len(line.split())>1:
                    kr_load_data(line.split()[1])
                else:
                    kr_load_data(kratedata_default_fn)
            elif "VAR" in loadwhat:
                if len(line.split())>1:
                    kr_load_vars(line.split()[1],krate_vars)
                else:
                    kr_load_vars(kratevar_default_fn,krate_vars)
            else:
                kr_print_message("Error: Cannot load '%s'" % loadwhat)
        else:
            kr_print_message("Error: load command expects at least one argument")
    def complete_load(self, text, line, begidx, endidx):
        LIST_ITEMS = [ 'var', 'data']
        if not text:
            completions = LIST_ITEMS[:]
        else:
            completions = [ f
                            for f in LIST_ITEMS
                            if f.startswith(text)
                            ]
        return completions

    def do_EOF(self, line):
        """ exits program"""
        kr_print_message("INFO: Thanks for using krate")
        fra1.ifclose()
        Vin1.ifclose()
        Load1.ifclose()
        Smbb1.ifclose()
        return True
    def postloop(self):
        pass
    def default(self,line):
        # unknown command. check if variable assignment was attempted
        line_executed=False
        if "=" in line:
            try:
                exec(line,krate_gvars,krate_vars)
                varx=line.split("=")[0]
                print " %s=%s" % (varx, str(krate_vars[varx]) )
                line_executed=True
            except:
                pass
        if line_executed==False:
            if line.split()[0] in valid_shell_commands:
                os.system(line)
            else:
                exit_code=1
                kr_print_message("ERROR: unsupported command '%s'" % line.split()[0])


# *************************************************************
# END of command line processing, start of functions area
# *************************************************************
def kr_print_message(info_str):
    print " %s" % info_str

def kr_list_vars(vars, pattern=""):
    if pattern=="":
        kr_print_message("INFO: Listing krate_cl variables")
    else:
        kr_print_message("INFO: Listing krate_cl variables matching '%s'"%pattern)
    for krate_var in sorted(krate_vars.keys()):
        if pattern=="" or (pattern in str(krate_var)):
            kr_print_message("      '%s' = '%s'" % (str(krate_var), str(krate_vars[krate_var])))

def kr_export_data(fn,objecttosave,overwrite=True):
    if (os.path.exists(fn) and overwrite==False):
        kr_print_message("INFO: krate data file already exists '%s'" % fn)
    else:
        kr_print_message("INFO: Export FRA data to '%s'" % fn)
##        try:
        book = xlwt.Workbook()
        # generate sheets, one per FRA data set
        keys=sorted(fra_data_dir.keys(),key=int)
        for index in keys:
            if fra_data_dir[index].valid:
                print "       Adding work-sheet '%s(%s)'" %(str(fra_data_dir[index].legend),str(index))
                sheet=book.add_sheet("%s(%s)" % (str(fra_data_dir[index].legend),str(index)))
                row=0; col=0
                sheet.write(row,col,"Generator:"); sheet.write(row,col+1,krate.krate_version())
                row+=1; sheet.write(row,col,"Name:"); sheet.write(row,col+1,fra_data_dir[index].name)
                row+=1; sheet.write(row,col,"Legend:"); sheet.write(row,col+1,fra_data_dir[index].legend)
                row+=1; sheet.write(row,col,"Date/Time:"); sheet.write(row,col+1,fra_data_dir[index].datetimestr)
                row+=1; sheet.write(row,col,"Author:"); sheet.write(row,col+1,fra_data_dir[index].author)
                row+=1; sheet.write(row,col,"DUT:"); sheet.write(row,col+1,fra_data_dir[index].dut)
                row+=1; sheet.write(row,col,"FRA Setup:"); sheet.write(row,col+1,fra_data_dir[index].frasetup)
                (pm,fc)=fra_data_dir[index].fr_data_det_pm()
                (gm,fgm)=fra_data_dir[index].fr_data_det_gm()
                row+=1; sheet.write(row,col,"PM:"); sheet.write(row,col+1,"%.1fdeg at fc =%.1fkHz" % (pm, fc/1e3))
                sheet.write(row,col+3,round(pm,1)); sheet.write(row,col+4,round(fc,1))
                row+=1; sheet.write(row,col,"GM:"); sheet.write(row,col+1,"%.1fdB at fc =%.1fkHz" % (gm, fgm/1e3))
                sheet.write(row,col+3,round(gm,1)); sheet.write(row,col+4,round(fgm,1))
                row+=1; sheet.write(row,col,"Sweep:"); sheet.write(row,col+1,"%s=%0.2f%s" % (fra_data_dir[index].sweep_var,fra_data_dir[index].sweep_value,fra_data_dir[index].sweep_unit))
                sheet.write(row,col+3,fra_data_dir[index].sweep_value)

                # write FRA data
                row=11
                sheet.write(row,col,"f");sheet.write(row,col+1,"Vch1(rms)");sheet.write(row,col+2,"Vch2(rms)")
                sheet.write(row,col+3,"gain(dB)");sheet.write(row,col+4,"phase(deg)")
                row+=1; col=0
                # note: we're not going to write all values received from the FRA (skip the last element, phase delay)
                for fratuple in fra_data_dir[index].frdata:
                    for i in range (0,len(fratuple)-1):
                        sheet.write(row,col+i,fratuple[i])
                    row+=1

                # write adjusted phase column
                row=11
                sheet.write(row,col+5,"phase_adj(deg)")
                row+=1; col=0
                (fc,db,ph_adjusted)=fra_data_dir[index].frdata_get_f_db_ph(ph_adjust=True)
                for i in range(0,len(ph_adjusted)):
                    sheet.write(row,col+5,ph_adjusted[i])
                    row+=1
                book.save(fn)
##        except:
##            kr_print_message("ERROR: writing to file '%s'" % fn)

def kr_save_data(fn,objecttosave,overwrite=True):
    if (os.path.exists(fn) and overwrite==False):
        kr_print_message("INFO: krate data file already exists '%s'" % fn)
    else:
        kr_print_message("INFO: Save FRA data to '%s'" % fn)
        try:
            f=open(fn,"wb")
            pickle.dump(objecttosave,f)
            f.close()
        except:
            kr_print_message("ERROR: writing to file '%s'" % fn)

def kr_load_data(fn):
    global fra_data_dir, fra_data_index
    try:
        f=open(fn,"rb")
        fra_data_dir={}
        fra_data_dir=pickle.load(f)
        f.close()
        # print "ok loaded object", fra_data_dir
        # krcmd.prompt="krate(%d)> " % len(fra_data_dir)
        if len(fra_data_dir)>0:
            # identify highest index
            fra_data_index=max(int(i) for i in fra_data_dir.keys())+1
        else:
            fra_data_index=0
        krcmd.prompt="krate(i=%d/c=%d)> " % (fra_data_index,len(fra_data_dir))
##        maxidx=0
##        if len(fra_data_dir)>0:
##            for idx in fra_data_dir.keys():
##                if int(idx)>maxidx:
##                    maxidx=int(idx)
##            fra_data_index=maxidx+1
##        else:
##            fra_data_index=0
        # print "fra_data_index=%d" % fra_data_index
        kr_print_message("INFO: %d FRA data sets loaded from '%s'" % (len(fra_data_dir),fn))
    except:
        kr_print_message("ERROR: reading from file '%s'" % fn)

def kr_save_vars(fn,vars,overwrite=True):
    if (os.path.exists(fn) and overwrite==False):
        kr_print_message("INFO: krate variable file '%s' already exists. Won't overwrite" % fn)
    else:
        kr_print_message("INFO: Save krate variables to '%s'" % fn)
        try:
            f=open(fn,"wt")
            f.write("# file created by '%s'\n" %krate.krate_version() )
            for krate_var in sorted(krate_vars.keys()):
                f.write(krate_var+"=")
                if isinstance(krate_vars[krate_var],str):
                    f.write("'%s'\n" % str(krate_vars[krate_var]))
                else:
                    f.write("%s\n" % str(krate_vars[krate_var]))
            f.close()
        except:
            kr_print_message("ERROR: writing to file '%s'" % fn)

def kr_load_vars(fn,vars):
    kr_print_message("INFO: Load krate variables from '%s'" % fn)
    try:
        f=open(fn,"rt")
        lineno=1
        for line in f:
            # print line.strip()
            try:
                exec(line,krate_gvars,krate_vars)
                lineno+=1
            except:
                kr_print_message("Error: Syntax in line %d" % lineno)
        f.close()
    except:
        kr_print_message("ERROR: reading from file '%s'" % fn)

def kr_list_serial_devices():
    if len(krate.find_usb_serial_devices())>0:
        kr_print_message("INFO: Listing available device communication ports")
        i=0
        for krate_dev in krate.find_usb_serial_devices():
            kr_print_message("      device[%d]='%s' (type '%s')" % (i,krate_dev[0],krate_dev[1])); i+=1
    else:
        kr_print_message("INFO: No device communication ports available")

def kr_list_smbb():
    if Smbb1.alive:
        kr_print_message("INFO: Listing SMBus bridge properties")
        kr_print_message("      smbb name='%s'" % Smbb1.instr_name)
        kr_print_message("      smbb interface='%s'" % Smbb1.ifname)
        kr_print_message("      smbb interface type='%s'" % Smbb1.iftype)
        addr_str=""
        for a in Smbb1.addr_pmbus:
            addr_str=addr_str+"0x%02x " % a
        if addr_str=="":
            addr_str="No devices found"
        kr_print_message("      smbb smbus addresses scan: %s" % addr_str)
        if Smbb1.addr_pmbus_active<>None:
            kr_print_message("      smbb active smbus address: 0x%02x" % Smbb1.addr_pmbus_active)
        addr_str=""
        for a in Smbb1.addr_pmbus_ara:
            addr_str=addr_str+"0x%02x " % a
        if addr_str=="":
            addr_str="No salrt requests"
        kr_print_message("      smbb salrt ARA addresses: %s" % addr_str)
    else:
        kr_print_message("INFO: No SMBus bridge device found")
        kr_print_message("      Connect device, then type 'smbb find'")

def kr_list_vin():
    if Vin1.alive:
        kr_print_message("INFO: Listing Vin instrument properties")
        kr_print_message("      Vin name='%s'" % Vin1.instr_name)
        kr_print_message("      Vin interface='%s'" % Vin1.ifname)
        kr_print_message("      Vin interface type='%s'" % Vin1.iftype)
    else:
        kr_print_message("INFO: No Vin supply found")
        kr_print_message("      Switch on and connect instrument, then type 'vin find'")

def kr_list_fra():
    if fra1.alive:
        kr_print_message("INFO: Listing FRA instrument properties")
        kr_print_message("      FRA name='%s'" % fra1.instr_name)
        kr_print_message("      FRA version='%s'" % fra1.instr_version)
        kr_print_message("      FRA interface='%s'" % fra1.ifname)
        kr_print_message("      FRA interface type='%s'" % fra1.iftype)
    else:
        kr_print_message("INFO: No FRA instruments found")
        kr_print_message("      Switch on and connect instrument, then type 'fra find'")

def kr_list_hal():
        global hal_addr
        kr_print_message("INFO: Listing defined HAL addresses")
        keys=sorted(hal_addr.keys())
        for i in keys:
            (hal_a,hal_m)=hal_addr[i]
            kr_print_message("      '%s' => hal_addr=0x%02x coefficient m=%dlsb/unit" % (i,hal_a,hal_m) )

def kr_list_reg(pattern=""):
    global registers_amba
    # check pattern string. if it contains a valid hex number, do an inverse register lookup i.e. provide the corresponding register name if there is one
    try:
        reg_addr=int(pattern,16)
    except:
        reg_addr=None
    if reg_addr:
        kr_print_message("INFO: List registers with an assigned address of 0x%04x" % reg_addr )
        keys=sorted(registers_amba.keys())
        for i in keys:
            if registers_amba[i]==reg_addr:
                kr_print_message("      '%s': address 0x%04X" % (i,reg_addr) )
    else:
        kr_print_message("INFO: Listing defined registers matching pattern '%s'" % pattern )
        keys=sorted(registers_amba.keys())
        for i in keys:
            if pattern in i:
                reg_addr=registers_amba[i]
                kr_print_message("      '%s': address 0x%04X" % (i,reg_addr) )

def kr_list_load():
    if Load1.alive:
        kr_print_message("INFO: Listing electronic load properties")
        kr_print_message("      el name='%s'" % Load1.instr_name)
        kr_print_message("      el interface='%s'" % Load1.ifname)
        kr_print_message("      el interface type='%s'" % Load1.iftype)
    else:
        kr_print_message("INFO: No electronic load found")
        kr_print_message("      Switch on and connect instrument, then type 'el find'")

def kr_list_data():
    keys=sorted(fra_data_dir.keys(),key=int)
    for i in keys:
        kr_show_info_fra(i,verbose=False)

def kr_create_fradata_name():
    try:
        name="vi=%.1f" % (float(krate_vars['vi']))
        name=name.replace(".","V")
    except:
        name="vi=%s" % krate_vars['vi']
    try:
        name+="_vo=%.1f" % (float(krate_vars['vo']))
        name=name.replace(".","V")
    except:
        name+="_vo=%s" % krate_vars['vo']
    try:
        name+="_io=%.1f" % (float(krate_vars['io']))
        name=name.replace(".","A")
    except:
        name+="_io=%s" % krate_vars['io']
    try:
        name+="_fsw=%.0fk" % (float(krate_vars['fsw']/1e3))
    except:
        name+="_fsw=%s" % krate_vars['fsw']
    try:
        name+="_ph=%d" % (int(krate_vars['ph']))
    except:
        name+="_ph=%s" % krate_vars['ph']
    try:
        name+="_of=%.0f" % (float(krate_vars['of']))
    except:
        name+="_of=%s" % krate_vars['of']
    try:
        name+="_a=%.2f" % (float(krate_vars['alpha']))
        name=name.replace(".","p")
    except:
        name+="_a=%s" % krate_vars['alpha']
    try:
        name+="_rdiv=%.3f" % (float(krate_vars['rdiv']))
        name=name.replace(".","p")
    except:
        name+="_rdiv=%s" % krate_vars['rdiv']
    name=name.replace(" ","_")
    # print "name='%s'" % name
    return name

def kr_show_info_fra(index,verbose=False):
    if fra_data_dir[index].valid:
        fmin=min(fra_data_dir[index].frdata_get_f())
        fmax=max(fra_data_dir[index].frdata_get_f())
        kr_print_message("INFO: Details of FRA data set '%s' with %d data points %.1fkHz..%.1fkHz" %(index,len(fra_data_dir[index].frdata),fmin/1e3,fmax/1e3) )
        kr_print_message("      name         = '%s'" % fra_data_dir[index].name )
        kr_print_message("      legend       = '%s'" % fra_data_dir[index].legend )
        kr_print_message("      date/time    = '%s'" % fra_data_dir[index].datetimestr )
        kr_print_message("      dut/author   = '%s' tested by '%s'" % (fra_data_dir[index].dut,fra_data_dir[index].author) )
        (pm,fc)=fra_data_dir[index].fr_data_det_pm()
        (gm,fgm)=fra_data_dir[index].fr_data_det_gm()
        kr_print_message("      phase margin = %.1fdeg at fc =%.1fkHz" % (pm, fc/1e3) )
        kr_print_message("      gain margin  = %.1fdB at fgm=%.1fkHz" % (gm, fgm/1e3) )
        sweep_var=fra_data_dir[index].sweep_var
        sweep_value=fra_data_dir[index].sweep_value
        sweep_unit=fra_data_dir[index].sweep_unit
        # if verbose, also show FRA data contents
        if verbose:
            for fratuple in fra_data_dir[index].frdata:
                # 6 data values per tuple: freq,mag1,mag2,db,phase,delay
                print ("f=%.1fHz mag1=%.3fV mag2=%.3fV db=%.1fdB phase=%.1fdeg delay=%.7fs" % fratuple)
        if sweep_var!="":
            kr_print_message("      sweep variable '%s'=%0.2f%s" % (sweep_var,sweep_value,sweep_unit))
    else:
        kr_print_message("INFO: Invalid FRA data set %d" %index )

def kr_write_pmfc(fn="frasweep.tmp", var=""):
    kr_print_message("INFO: Writing FRA sweep data to '%s'" % fn)
    keys=sorted(fra_data_dir.keys(),key=int)
    f=open(fn,"wt")
    if var=="":
        # deal with un-sweeped data some other day
        pass
    else:
        for index in keys:
            if fra_data_dir[index].valid and (fra_data_dir[index].sweep_var==var):
                (pm,fc)=fra_data_dir[index].fr_data_det_pm()
                sweep_value=fra_data_dir[index].sweep_value
                sweep_unit=fra_data_dir[index].sweep_unit
                kr_print_message("      Adding FRA %s-sweep data set '%s': %s=%.2f%s pm=%.1fdeg/fc=%.1fkHz" %(var,str(index),var,sweep_value,sweep_unit,pm,fc/1e3))
                f.write("%f %f %f\n" % (sweep_value,pm,fc))
    f.close()
def kr_write_fra(index,fn="fradat.tmp",overwrite=True,ph_adjust=True):
    if (os.path.exists(fn) and overwrite==False):
        kr_print_message("INFO: FRA data file already exists '%s'" % fn)
        return
    if fra_data_dir[index].valid:
        try:
            f=open(fn,"wt")
            (freq,db,ph)=fra_data_dir[index].frdata_get_f_db_ph()
            ph_adjusted=fra_data_dir[index].frdata_ph_adjust(ph)
            for i in range(0,len(freq)):
                f.write("%f %f %f\n" % (freq[i],db[i],ph_adjusted[i]))
            f.close()
        except:
            f.close()
            kr_print_message("ERROR: writing to file '%s'" % fn)
    else:
        kr_print_message("INFO: Invalid FRA data set %d" %index )

def kr_write_smbbreg(fn="smbbambareg",values=None,overwrite=True):
    if (os.path.exists(fn) and overwrite==False):
      kr_print_message("INFO: File already exists '%s'" % fn)
      return
    try:
	f=open(fn+".tmp","wt")
	for i in range(0,len(values)):
	    f.write("%f\n" % (values[i]))
	f.close()
    except:
	f.close()
	kr_print_message("ERROR: writing to file '%s'" % fn)

def kr_determine_axis_settings(vmin,vmax):
  # determine "pretty" axis settings to cater for values between vmin and vmax
  span=vmax-vmin
  if vmin==0 and vmax==0:
    xmin=-0.5; xmax=0.5; xgrid=0.25;
  else:
    if span==0:
      n10=numpy.floor(numpy.log10(abs(vmin))); k10=vmin/(10**n10);
      xmin=numpy.floor(k10*10)*(10**(n10-1)); xmax=(numpy.floor(k10*10)+1)*(10**(n10-1)); xgrid=(xmax-xmin)/2;
    else:
      n10=numpy.floor(numpy.log10(span)); k10=span/(10**n10); m10=1
      #Adjustment 1: If k10 smaller than 2, scale it up by a factor of 10, and adjust n10
      if (k10<1.5):
	n10=n10-1; k10=k10*10
      #Adjustment 2: If k10 smaller than 5, scale down m10 and adjust k10 upwards
      if (k10<4):
	m10=m10/4.0; k10=k10*4
      #Determine axis settings
      # print "n10=%f k10=%f, m10=%f" % (n10,k10,m10)
      xgrid=m10*(10**n10)
      xspan=m10*(numpy.floor(k10)+2)*(10**n10)
      xmin=vmin-numpy.mod(vmin,m10*(10**n10))
      xmax=xmin+xspan
  return (xmin,xgrid,xmax)

def kr_write_gnuplot_hist(fn="smbbambareg", values=None, reginfostr="r", devinfostr="", devtelestr="", statstr="", exe_gnuplot=False, color="green"):
	    vmin=min(values)
	    vmax=max(values)
	    (xmin,xgrid,xmax)=kr_determine_axis_settings(vmin,vmax)
	    bins=5*abs((xmax-xmin)/xgrid)
            kr_print_message("INFO: Writing GNUPLOT histogram script to '%s'" % (fn+".gp"))
            # kr_print_message("      Histogram parameters: xmin=%.1f xmax=%.1f xgrid=%.1f bins=%.1f given data %.1f..%.1f" % (xmin,xmax,xgrid,bins,vmin,vmax))
            f=open(fn+".gp","wt")
            gp_str=""
            gp_str+='# GNUPLOT script generated by %s' % krate.krate_version()
            gp_str+='\n'+'# Register:  %s' % reginfostr
            gp_str+='\n'+'# Device:    %s' % devinfostr
            gp_str+='\n'+'# Telemetry: %s' % devtelestr
            gp_str+='\n'+'# Stats:     %s (%.0f bins)' % (statstr,bins)
            gp_str+='\n'+'set terminal wxt size %d,%d'%(krate_vars['bp_sizex'],krate_vars['bp_sizey']/2)
            gp_str+='\n'+'bins=%f' % bins
            gp_str+='\n'+'max=%f' % xmax
            gp_str+='\n'+'min=%f' % xmin
            gp_str+='\n'+'width=(max-min)/bins'
            gp_str+='\n'+'hist(x,width)=width*floor(x/width)+width/2.0'
            gp_str+='\n'+'set xrange [min:max]'
            gp_str+='\n'+'set yrange [0:]'
            # gp_str+='\n'+'set offset graph 0.05,0.05,0.05,0.0'
            # gp_str+='\n'+'set xtics min,%f,max' % xgrid
            gp_str+='\n'+'set xtics %f,%f,%f' % (xmin,xgrid,xmax)
            gp_str+='\n'+'set boxwidth width'
            gp_str+='\n'+'set style fill solid 0.5'
            gp_str+='\n'+'set tics out nomirror'
            gp_str+='\n'+'set style line 1 lt rgb "red" lw 2'
            gp_str+='\n'+'set style line 20 lt rgb "gray90" lw 1'
            gp_str+='\n'+'set grid x y ls 20, ls 20'
            gp_str+='\n'+'set grid xtics ytics'
            gp_str+='\n'+'set grid mxtics mytics'
            # gp_str+='\n'+'set lmargin 10'
            gp_str+='\n'+'set bmargin 10'
            gp_str+='\n'+'set xlabel "%s"' % reginfostr
            gp_str+='\n'+'set ylabel "#"'
            gp_str+='\n'+'plot "%s" u (hist($1,width)):(1.0) smooth freq w boxes lc rgb"%s" notitle' % (fn+".tmp",color)
            gp_str+='\n'+'set label "%s (%.0f bins)" at GPVAL_X_MIN,-GPVAL_Y_MAX/10*2.5 tc rgb "gray80"' % (statstr,bins)
            gp_str+='\n'+'set label "%s" at GPVAL_X_MIN,-GPVAL_Y_MAX/10*3.0 tc rgb "gray80"' % (devtelestr)
            gp_str+='\n'+'set label "%s" at GPVAL_X_MIN,-GPVAL_Y_MAX/10*3.5 tc rgb "gray80"' % (devinfostr)
            gp_str+='\n'+'set label "%s" at GPVAL_X_MIN,-GPVAL_Y_MAX/10*4.0 tc rgb "gray80"' % (krate.krate_version())
            gp_str+='\n'+'replot'
            f.write(gp_str)
            f.close()
            if exe_gnuplot:
                retcode = os.system("which gnuplot >> /dev/null")
                if (retcode==0):
                    os.system("gnuplot %s -p" % (fn+".gp"))

def kr_write_gnuplot_pmfc(fn="kratesweep.gp",fn_data="", xvar="x", xunit="", dut="dut", exe_gnuplot=False):
            kr_print_message("INFO: Writing GNUPLOT script to '%s'" % fn)
            f=open(fn,"wt")
            gp_str=""
            gp_str+='# GNUPLOT script generated by %s' % krate.krate_version()
            # gp_str+='\n'+'set terminal wxt size 1000,1000'
            gp_str+='\n'+'set terminal wxt size %d,%d'%(krate_vars['bp_sizex'],krate_vars['bp_sizey']/2)
            gp_str+='\n'+'set style line 1 lt rgb "red" lw 2'
            gp_str+='\n'+'set style line 2 lt rgb "blue" lw 2'
            gp_str+='\n'+'set style line 20 lt rgb "gray60" lw 1'
            gp_str+='\n'+'set style line 21 lt rgb "gray90" lw 1'
            gp_str+='\n'+'set grid x y ls 20, ls 21'
            gp_str+='\n'+'set grid xtics ytics'
            gp_str+='\n'+'set grid mxtics mytics'
            gp_str+='\n'+'set lmargin 10'
            gp_str+='\n'+'set xlabel "%s in [%s]"'%(xvar,xunit)
            gp_str+='\n'+'set ylabel "phase margin (pm) in [dB]"'
            gp_str+='\n'+'set y2label "cross-over frequency (fc) in [Hz]"'
            gp_str+='\n'+'set key right top box'
            gp_str+='\n'+'set yrange [%f:%f]' % (0,9*10)
            gp_str+='\n'+'set y2range [%f:%f]' % (0,9*10e3)
            gp_str+='\n'+'set y2tics nomirror'
            legend=' pm in [dB]'
            gp_str+='\n'+'plot\\\n'
            gp_str+='"%s" using 1:2 with lines title "%s" ls 1,\\\n' %(fn_data,legend)
            legend=' fc in [Hz]'
            gp_str+='"%s" using 1:3 with lines axes x1y2 title "%s" ls 2' %(fn_data,legend)
            gp_str+='\n'+'set label "%s" at GPVAL_X_MIN+(GPVAL_X_MAX-GPVAL_X_MIN)/100,GPVAL_Y_MAX-3 tc rgb "gray80"' % (krate.krate_version())
            gp_str+='\n'+'set label "DUT: %s" at GPVAL_X_MIN+(GPVAL_X_MAX-GPVAL_X_MIN)/100,GPVAL_Y_MAX-8 tc rgb "gray80"' % (dut)
            gp_str+='\n'+'replot'
            f.write(gp_str)
            f.close()
            if exe_gnuplot:
                retcode = os.system("which gnuplot >> /dev/null")
                if (retcode==0):
                    os.system("gnuplot %s -p" % fn)

def kr_write_gnuplot(fra_indices,fn="krate.gp",exe_gnuplot=False):
##        try:
            kr_print_message("INFO: Writing GNUPLOT script to '%s'" % fn)
            f=open(fn,"wt")
            gp_str=""
            gp_str+='# GNUPLOT script generated by %s' % krate.krate_version()
            gp_str+='\n'+'set terminal wxt size %d,%d'%(krate_vars['bp_sizex'],krate_vars['bp_sizey'])
            gp_str+='\n'+'set style line 1 lt rgb "red" lw 2'
            gp_str+='\n'+'set style line 2 lt rgb "blue" lw 2'
            gp_str+='\n'+'set style line 3 lt rgb "orange" lw 2'
            gp_str+='\n'+'set style line 4 lt rgb "dark-green" lw 2'
            gp_str+='\n'+'set style line 5 lt rgb "magenta" lw 2'
            gp_str+='\n'+'set style line 6 lt rgb "brown" lw 2'
            gp_str+='\n'+'set style line 7 lt rgb "violet" lw 2'
            gp_str+='\n'+'set style line 8 lt rgb "turquoise" lw 2'
            gp_str+='\n'+'set style line 9 lt rgb "gold" lw 2'
            gp_str+='\n'+'set style line 10 lt rgb "black" lw 2'
            gp_str+='\n'+'set style line 11 lt rgb "royalblue" lw 2'
            gp_str+='\n'+'set style line 12 lt rgb "gold" lw 2'
            gp_str+='\n'+'set style line 13 lt rgb "cyan" lw 2'
            gp_str+='\n'+'set style line 14 lt rgb "dark-pink" lw 2'
            gp_str+='\n'+'set style line 15 lt rgb "coral" lw 2'
            gp_str+='\n'+'set style line 16 lt rgb "dark-khaki" lw 2'
            gp_str+='\n'+'set style line 17 lt rgb "olive" lw 2'
            gp_str+='\n'+'set style line 18 lt rgb "sandybrown" lw 2'
            gp_str+='\n'+'set style line 19 lt rgb "lemonchiffon" lw 2'
            gp_str+='\n'+'set style line 20 lt rgb "gray60" lw 1'
            gp_str+='\n'+'set style line 21 lt rgb "gray90" lw 1'
            gp_str+='\n'+'set logscale x'
            gp_str+='\n'+'set grid ls 20, ls 21'
            gp_str+='\n'+'set grid xtics ytics'
            gp_str+='\n'+'set grid mxtics mytics'
            gp_str+='\n'+'set multiplot layout 2,1'
            gp_str+='\n'+'set lmargin 10'
            gp_str+='\n'+'set ylabel "gain in [dB]"'
            gp_str+='\n'+'set key right top box'
            gp_str+='\n'+'set yrange [%f:%f]' % (krate_vars['bp_dbmin'],krate_vars['bp_dbmax'])
            gp_str+='\n'+'plot\\\n'
            i=0
            for idx in fra_indices:
                legend=fra_data_dir[idx].legend
                (pm,fc)=fra_data_dir[idx].fr_data_det_pm()
                legend+=" (pm=%.1fdeg @ fc=%.1fkHz)" % (pm,fc/1e3)
                gp_str+='"fra_%s.tmp" using 1:2 with lines smooth csplines title "%s" ls %d' %(idx,legend,i+1)
                if i==len(fra_indices)-1:
                    pass
                else:
                    gp_str+=',\\\n'
                i+=1
            gp_str+='\n'+'set xlabel "f in [Hz]"'
            gp_str+='\n'+'set ylabel "phase in [deg]"'
            gp_str+='\n'+'set key off'
            gp_str+='\n'+'set label "%s" at GPVAL_X_MIN*1.1,%f tc rgb "gray80"' % (krate.krate_version(),krate_vars['bp_phmin']+12)
            dutstr=fra_data_dir[fra_indices[0]].dut+"/"+fra_data_dir[fra_indices[0]].author+"/"+fra_data_dir[fra_indices[0]].frasetup
#            gp_str+='\n'+'set label "DUT: %s" at GPVAL_X_MAX,%f tc rgb "gray80" right' % (dutstr,krate_vars['bp_phmax']+12)
            gp_str+='\n'+'set label "DUT: %s" at GPVAL_X_MIN*1.1,%f tc rgb "gray80"' % (dutstr,krate_vars['bp_phmax']+12)
            gp_str+='\n'+'set yrange [%f:%f]' % (krate_vars['bp_phmin'],krate_vars['bp_phmax'])
            gp_str+='\n'+'plot\\\n'
            i=0
            for idx in fra_indices:
                gp_str+='"fra_%s.tmp" using 1:3 with lines smooth csplines notitle ls %d' %(idx,i+1)
                if i==len(fra_indices)-1:
                    pass
                else:
                    gp_str+=',\\\n'
                i+=1
            gp_str+='\n'+'unset multiplot'

            f.write(gp_str)
            f.close()
            if exe_gnuplot:
                retcode = os.system("which gnuplot >> /dev/null")
                if (retcode==0):
                    os.system("gnuplot %s -p" % fn)

##        except:
##            f.close()
##            kr_print_message("ERROR: writing to file '%s'" % fn)

def kr_fra_get(showplot=True):
        global fra_data_index
        if showplot:
            kr_print_message("INFO: Obtaining data from FRA")
        fradata=fra1.get_data()
        if len(fradata)>0:
            # first, add a new FraData object to directory
            index=str(fra_data_index)
            fra_data_dir[index]=krate.FraData()
            fra_data_dir[index].add_frdata(fradata)
            fra_data_dir[index].name=kr_create_fradata_name()
            if krate_vars['legend']=="":
                fra_data_dir[index].legend="fra(%s)"%index
            else:
                fra_data_dir[index].legend=krate_vars['legend']
            fra_data_dir[index].dut=krate_vars['dut']
            fra_data_dir[index].author=krate_vars['author']
            fra_data_dir[index].datetimestr=time.asctime()
            fra_data_dir[index].frasetup="Inj. mode='%s', level=%.1fmV, tol=%.1f%%, speed '%s'"%(
                krate_vars['vinject_mode'],krate_vars['vinject_lvl']*1e3,krate_vars['vinject_tol'],krate_vars['speed'])
            fra_data_dir[index].sweep_var=krate_vars['fra_sweep_var']
            fra_data_dir[index].sweep_value=krate_vars['fra_sweep_value']
            fra_data_dir[index].sweep_unit=krate_vars['fra_sweep_unit']
            kr_show_info_fra(index)
            if showplot:
                kr_write_fra(index,fn="fra_%s.tmp" % index,overwrite=True,ph_adjust=True)
                kr_write_gnuplot([index],fn="krateget.gp",exe_gnuplot=True)
            fra_data_index+=1
            # krcmd.prompt="krate(%d)> " % len(fra_data_dir)
            krcmd.prompt="krate(i=%d/c=%d)> " % (fra_data_index,len(fra_data_dir))
        else:
            kr_print_message("INFO: Invalid FRA data. Run measurement again")

def kr_fra_import(fn="import.fra"):
    try:
        f=open(fn,"rt")
        kr_print_message("INFO: Importing FRA data from file '%s'" % fn)
        lineno=1; data_valid=True
        section_n=1; section_in_preamble=True; data_records=[];
        for line in f:
            # remove comments and strip
            line=line.split("//",1)[0].strip()
            if line=="":
                pass
            elif "=" in line:
                if section_in_preamble==False and len(data_records)>0:
                    # we have previously recorded data now, and have finished reading the data section
                    # print data_records
                    if data_valid:
                        kr_fra_store(data_records)
                # kr_print_message("INFO: Assignment '%s'" % line)
                try:
                    exec(line,krate_gvars,krate_vars)
                    varx=line.split("=")[0]
                    if section_in_preamble==False:
                        # print first assignment per data record for informational purposes
                        # kr_print_message("INFO: %s='%s'" % (varx, str(krate_vars[varx]) ))
                        pass
                except:
                    data_valid=False
                    pass
                section_in_preamble=True;
                data_records=[]
            else:
                # assume we're looking at a data record now. try to tuple-ize it
                # kr_print_message("INFO: Data record '%s'" % line)
                try:
                   imported_tuple=tuple([float(i) for i in line.split(",")])
                except:
                    dont_save=True
                    kr_print_message("ERROR: In line #%d: '%s'" % (lineno,line))
                    
                section_in_preamble=False
                data_records.append(imported_tuple)
            lineno+=1
        f.close()
        if data_valid:
            kr_fra_store(data_records)
    except:
        kr_print_message("ERROR: Can't find FRA data file '%s'" % fn)

def kr_fra_store(fradata=()):
    global fra_data_index
    global fra_data_dir
    if len(fradata)>0:
        # first, add a new FraData object to directory
        index=str(fra_data_index)
        fra_data_dir[index]=krate.FraData()
        fra_data_dir[index].add_frdata(fradata)
        fra_data_dir[index].name=kr_create_fradata_name()
        if krate_vars['legend']=="":
            fra_data_dir[index].legend="fra(%s)"%index
        else:
            fra_data_dir[index].legend=krate_vars['legend']
        fra_data_dir[index].dut=krate_vars['dut']
        fra_data_dir[index].author=krate_vars['author']
        fra_data_dir[index].datetimestr=time.asctime()
        fra_data_dir[index].frasetup="n/a (imported record)"
        fra_data_dir[index].sweep_var=krate_vars['fra_sweep_var']
        fra_data_dir[index].sweep_value=krate_vars['fra_sweep_value']
        fra_data_dir[index].sweep_unit=krate_vars['fra_sweep_unit']
        kr_show_info_fra(index)
        fra_data_index+=1
        krcmd.prompt="krate(i=%d/c=%d)> " % (fra_data_index,len(fra_data_dir))

def kr_fra_wait():
        completion_prev=-100
        try:
            while True:
                completion=fra1.sweep_check_completion(krate_vars['fstart'],krate_vars['fstop'])
                if completion<0:
                    kr_print_message("INFO: FRA has no data")
                    break
                elif completion>=100:
                    kr_print_message("INFO: FRA complete")
                    break
                if (completion-completion_prev)<25:
                    pass
                else:
                    completion_prev=(completion//25)*25
                    kr_print_message("INFO: Waiting for FRA to complete: %3.0f%%" % ((completion//25)*25))
                time.sleep(0.5)
        except KeyboardInterrupt:
            fra1.sweep("stop")
            kr_print_message("\r INFO: FRA aborted on user request")

def kr_import_register_definitions(fn):
    global registers_amba
    try:
        f=open(fn,"rt")
        kr_print_message("INFO: Import register definitions from '%s'" % fn )
        lineno=1;equno=0;
        for line in f:
            lineno+=1;
            # remove comments and strip
            line=line.split(";",1)[0].strip()
            if line=="":
                pass
            else:
                linesplit=line.split()
                 # 0023 =                 r_pmbus_vout_command			equ	i
                if "equ" in linesplit and linesplit[1]=="=":
                    equname=linesplit[2]
                    if equname.islower():
                        try:
                            equno+=1
                            equvalue=int(linesplit[0],16)
                            # print "%04d: '%s'=0x%04X" % (equno,equname,equvalue)
                            if registers_amba.has_key(equname):
                                pass
                            else:
                                registers_amba[equname]=equvalue
                        except:
                            equvalue=None
        kr_print_message("INFO: %d lines processed, %d definitions imported" % (lineno,equno) )
        f.close()
    except:
        kr_print_message("ERROR: Can't find LST file '%s'" % fn)

if __name__ == '__main__':
    os.system("clear")
    welcome_str="* Welcome to %s *" % krate.krate_version()
    welcome_frame="*"*len(welcome_str)
    print welcome_frame
    print welcome_str
    print welcome_frame
    kr_print_message("HELP: Type 'help [command]' if you're lost. Enjoy!\n")

    kr_print_message("      17/01/2014 ->v0.84 Support register histograms (smbb hist[u])")
    kr_print_message("      04/01/2014 v0.82 Support u2i ARA feature (smbb ara)")
    kr_print_message("      04/01/2014 v0.80 Support u2i ARA feature (smbb ara)")
    kr_print_message("      03/01/2014 v0.76 Add Arduino u2i support (incl. smbb stat)")
    kr_print_message("      09/08/2013 vx.xx Add smbb phases[={1,2}]")
    kr_print_message("      07/08/2013 vx.xx Added list reg inverse lookup, provide address as hex")
    kr_print_message("      07/08/2013 vx.xx Added smbb info_dsp, smbb stat. Process krate.init at startup")
    kr_print_message("      22/05/2013 vx.xx Support for Tektronix AFG3022B function generator\n")

    # if default variable file not already exists in directory, create it
    kr_save_vars(kratevar_default_fn,krate_vars,overwrite=False)
    # load default variable file
    kr_load_vars(kratevar_default_fn,krate_vars)

    krcmd=KrateCmd()
    krcmd.prompt="krate(i=%d/c=%d)> " % (fra_data_index,len(fra_data_dir))
    krcmd.onecmd("fra find")
    krcmd.onecmd("vin find")
    krcmd.onecmd("el find")
    krcmd.onecmd("smbb find")

    fn="krate.init"     # process command file, if it exists
    if os.path.exists(fn):
        f=open(fn,"rt")
        kr_print_message("INFO: Execute commands from file '%s'" % fn )
        for line in f:
            line_wo_comments=line.split("#")[0].strip()
            if (line_wo_comments!=""):
                krcmd.onecmd(line_wo_comments)
        f.close()
    else:
        kr_print_message("HINT: You may use command file '%s' for extra convenience" % fn )

    krcmd.cmdloop()
