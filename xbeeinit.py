"""
The MIT License (MIT)
Copyright (c) <2014> <Alan Marchiori>
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
    The above copyright notice and this permission notice shall be included in
    all copies or substantial portions of the Software.
    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
    THE SOFTWARE.
"""

"""
This program tries to initialize a new (factory reset) XBee 
so it can be used with xbeechat.

We have to change the baud rate, enable API mode, and setup
acknowledgments.

Only works with python2.

Alan Marchiori
1/15/2015 - created 
"""
import os
import logging
import serial
import time

logging.basicConfig(level=logging.INFO)
bauds = [9600,38400, 115200, 57600, 1200, 2400, 4800, 19200 ]
def get_devs(prefix=['ttyUSB', 'ttyACM'], root='/dev'):
    devs = []
    for pr in prefix:
        devs += [os.path.join(root, y) for y in filter(lambda x: x.startswith(pr), os.listdir(root))]
    return devs
def send_command(device, atcmd = "AT", timeout = 1):
    store = device.timeout # store old value
    device.timeout = timeout
    
    logging.debug("tx: [{}]: {}".format(len(atcmd), atcmd))
    device.write(atcmd)
    rslt = device.read(128).replace('\r', '')
    logging.debug("rx: [{}]: {}".format(len(rslt), rslt))
    device.timeout = store # restore value
    return rslt
def try_configure(dev, baud = 9600):
    # default xbee settings are 9600 baud, 8, n, 1
    s = serial.Serial(dev, baud, timeout=1)
    
    logging.info("Trying {} at {} baud".format(dev, baud))
    
    #command mode as 1 second guard on either side of +++
    time.sleep(1)
    s.write("+++")
    time.sleep(1)
    
    rsp = s.read(2)    
    logging.debug("rx: {}".format(rsp))
    
    if rsp == "OK":
        # entered command mode. setup now
        for cmd in ['ATBD5\r',  #set baud to 38400
                    'ATAP2\r',  # api mode with escapted chars
                    'ATMM2\r',  # mac mode 2 (802.15.4) w/ acks
                    'ATWR\r',   # write
                    'ATCN\r']: # exit
            logging.debug("{} got: {}".format(cmd, send_command(s, cmd, timeout=1)))
        return True
    else:
        return False
    
for dev in get_devs():
    logging.info("Found USB device at {}".format(dev))

    for b in bauds:
        if try_configure(dev, baud = b):
            logging.info("Success")
            break


#if __name__ == "__main__":
    #init()