# analyze_pcap.py
import sys, subprocess, json, csv
if len(sys.argv)<2:
    print("Usage: python analyze_pcap.py file.pcap")
    sys.exit(1)
pcap=sys.argv[1]
# use tshark to get protocol hierarchy statistics in JSON-like
cmd=['tshark','-r',pcap,'-q','-z','io,phs']
proc=subprocess.run(cmd, capture_output=True, text=True)
print(proc.stdout)
# quick: count frames and bytes
cmd2=['tshark','-r',pcap,'-q','-z','io,stat,0']
proc2=subprocess.run(cmd2, capture_output=True, text=True)
print(proc2.stdout)
