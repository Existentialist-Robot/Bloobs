# """
# Blueberry, cayden
# """

# import sys
# import logging
# import asyncio
# import platform
# import bitstring
# import argparse
# import time
# import signal
# import atexit

# from bleak import BleakClient 
# from bleak import _logger as logger

# from Blueberry import Blueberry

# global bby, bby_task, bby_killer_task, save_file

# def my_callback(data):
#     """
#     This is called and passed the blueberry data evertime a new data point is received by the Blueberry over bluetooth

#     All we do here is save the data to a csv
#     """
#     idx = data["packet_index"]
#     path = data["path"]
#     c1 = data["channel1"]
#     c2 = data["channel2"]
#     c3 = data["channel3"]

#     if data["path"] == "long_path" and data["big"] == True:
#             save_file.write("{},{},{},{},{},{}\n".format(time.time(), idx, path, c1, c2, c3))
#     else:
#             save_file.write("{},{},{},{},{},{}\n".format(time.time(), idx, path, c1, c2, c3))


# async def sleeper(bby):
#     """
#     This runs for 25 seconds then kills the blueberry connection. It's just here for an example of how to asynchronously terminate the Blueberry.
#     """
#     for i in range(0, 25):
#         print(i)
#         await asyncio.sleep(1)
#     await bby.stop()

# async def main():
#     global bby, bby_task, bby_killer_task, save_file

#     parser = argparse.ArgumentParser()
#     parser.add_argument("-a","--address", help="MAC address of the blueberry")
#     parser.add_argument("-d", "--debug", help="debug", action='store_true')
#     args = parser.parse_args()

#     #get address
#     mac = args.address

#     #get debug
#     debug=args.debug

#     save_file = open("{}.csv".format(time.time()), "w+")
#     save_file.write("timestamp,idx,path,c1,c2,c3\n")
 
#     #create blueberry instance
#     bby = Blueberry(mac, callback=my_callback, debug=debug)

#     #start a task to connect to and stream from the blueberry
#     bby_task = asyncio.create_task(bby.run())
#     #start a task that waits 15 seconds and then terminates the blueberry task
#     bby_killer_task = asyncio.create_task(sleeper(bby))
#     #setup program killer
#     #signal.signal(signal.SIGINT, signal_handler)

#     await bby_task, bby_killer_task
#     save_file.close()

# async def shutdown():
#     global bby, bby_task, bby_killer_task
#     bby_killer_task.cancel()
#     await bby.stop()
#     await bby_task, bby_killer_task

# if __name__ == "__main__":
#     #create asyncio event loop and start program
#     loop = asyncio.get_event_loop()

#     #handle kill events (Ctrl-C)
#     for signame in ('SIGINT', 'SIGTERM'):
#         loop.add_signal_handler(getattr(signal, signame),
#                                 lambda: asyncio.ensure_future(shutdown()))
#     #start program loop
#     try:
#         loop.run_until_complete(main())
#     finally:
#         loop.close()

# -*- coding: utf-8 -*-
# """
# cayden, Blueberry
# hbldh <henrik.blidh@gmail.com>, BLEAK
# """

import sys
import logging
import asyncio
import platform
import bitstring
import argparse
import time

from bleak import BleakClient 
from bleak import _logger as logger

#Blueberry glasses GATT server characteristics information
bbxService={"name": 'fnirs service',
            "uuid": '0f0e0d0c-0b0a-0908-0706-050403020100' }
bbxchars={
          "commandCharacteristic": {
              "name": 'write characteristic',
                  "uuid": '1f1e1d1c-1b1a-1918-1716-151413121110',
                  "handles": [None],
                    },
            "shortFnirsCharacteristic": {
                    "name": 'short_path',
                        "uuid": '2f2e2d2c-2b2a-2928-2726-252423222120',
                        "handles": [19, 20, 47],
                          },
            "longFnirsCharacteristic": {
                    "name": 'long_path',
                        "uuid": '3f3e3d3c-3b3a-3938-3736-353433323130',
                        "handles": [22, 23, 51],
                          }

            }
SHORT_PATH_CHAR_UUID = bbxchars["shortFnirsCharacteristic"]["uuid"]
LONG_PATH_CHAR_UUID = bbxchars["longFnirsCharacteristic"]["uuid"]

stream = True
save = False
debug = False
save_file = None

#unpack fNIRS byte string
def unpack_fnirs(sender, packet):
    global bbxchars
    data = dict()
    data["path"] = None
    #figure out which characteristic sent it (using the handle, why do we have UUID AND handle?)
    for char in bbxchars:
        if sender in bbxchars[char]["handles"]:
            data["path"] = bbxchars[char]["name"]
            break
        elif type(sender) == str and sender.lower() == bbxchars[char]["uuid"]:
            data["path"] = bbxchars[char]["name"]
            break
    if data["path"] == None:
        print("Error unknown handle number: {}. See: https://github.com/blueberryxtech/BlueberryPython/issues/1 or reach out to cayden@blueberryx.com".format(sender))
        return None
    #unpack packet
    aa = bitstring.Bits(bytes=packet)
    if data["path"] == "long_path" and len(packet) >= 21:
        pattern = "uintbe:8,uintbe:8,intbe:32,intbe:32,intbe:32,uintbe:8,uintbe:8,uintbe:8,uintbe:8,uintbe:8,intbe:16"
        res = aa.unpack(pattern)
        data["packet_index"] = res[1]
        data["channel1"] = res[2] #740/940
        data["channel2"] = res[3] #880
        data["channel3"] = res[4] #850
        data["sp"] = res[5]
        data["dp"] = res[6]
        data["hr"] = res[7]
        data["hrv"] = res[8]
        data["ml"] = res[9]
        data["temperature"] = res[10]
        data["big"] = True #big: whether or not the extra metrics were packed in
    else:
        pattern = "uintbe:8,uintbe:8,intbe:32,intbe:32,intbe:32,uintbe:8,uintbe:8"
        res = aa.unpack(pattern)
        data["packet_index"] = res[1]
        data["channel1"] = res[2] #740/940
        data["channel2"] = res[3] #880
        data["channel3"] = res[4] #850
        data["big"] = False #big: whether or not the extra metrics were packed in
    return data

def notification_handler(sender, data):
    global save, debug
    """Simple notification handler which prints the data received."""
    data = unpack_fnirs(sender, data)
    idx = data["packet_index"]
    path = data["path"]
    c1 = data["channel1"]
    c2 = data["channel2"]
    c3 = data["channel3"]

    if data["path"] == "long_path" and data["big"] == True:
        sp = data["sp"]
        dp = data["dp"]
        hr = data["hr"]
        hrv = data["hrv"]
        ml = data["ml"]
        temperature = data["temperature"]

    if save:
        if data["path"] == "long_path" and data["big"] == True:
                save_file.write("{},{},{},{},{},{}\n".format(time.time(), idx, path, c1, c2, c3))
        else:
                save_file.write("{},{},{},{},{},{}\n".format(time.time(), idx, path, c1, c2, c3))

    if debug:
        if data["path"] == "long_path" and data["big"] == True:
            print("Blueberry: {}, path: {}, index: {}, C1: {}, C2: {}, C3: {}, SP : {}, DP : {}, HR : {}, HRV : {}, ML : {}, temperature : {},".format(sender, path, idx, c1, c2, c3, sp, dp, hr, hrv, ml, temperature))
        else:
            print("Blueberry: {}, path: {}, index: {}, C1: {}, C2: {}, C3: {}".format(sender, path, idx, c1, c2, c3))

async def run(address, debug=False):
    global stream
    if debug:
        l = logging.getLogger("asyncio")
        l.setLevel(logging.DEBUG)
        h = logging.StreamHandler(sys.stdout)
        h.setLevel(logging.DEBUG)
        l.addHandler(h)
        logger.addHandler(h)

    print("Trying to connect...")
    async with BleakClient(address) as client:
        x = await client.is_connected()
        logger.info("Connected to: {0}".format(x))

        await client.start_notify(SHORT_PATH_CHAR_UUID, notification_handler)
        await client.start_notify(LONG_PATH_CHAR_UUID, notification_handler)
        while stream:
            await asyncio.sleep(0.1)
        await client.stop_notify(CHARACTERISTIC_UUID)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-a","--address", help="MAC address of the blueberry")
    parser.add_argument("-s","--save", help="If present, save", action='store_true')
    parser.add_argument("-f","--filename", help="Name of file to save to", type=str)
    parser.add_argument("-d", "--debug", help="debug", action='store_true')
    args = parser.parse_args()

    #get address
    mac = args.address

    #should we debug?
    if args.debug:
        debug = True

    #if we should save, and make the save file
    if args.save:
        save = True
        if not args.filename or args.filename == "":
            save_file = open("{}.csv".format(time.time()), "w+")
        else:
            save_file = open(args.filename, "w+")
        save_file.write("timestamp,idx,path,c1,c2,c3\n")

    #translate address to be multi-platform
    address = (
        mac # <--- Change to your device's address here if you are using Windows or Linux
        if platform.system() != "Darwin"
        else mac # <--- Change to your device's address here if you are using macOS
    )

    #start main loop
    loop = asyncio.get_event_loop()
    # loop.set_debug(True)
    loop.run_until_complete(run(address, debug=True))