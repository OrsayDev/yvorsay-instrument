import numpy
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import serial
import os
import json

abs_path = os.path.abspath(os.path.join((__file__ + "/../../nionswift_plugin/laser_mod/"), "global_settings.json"))
with open(abs_path) as savfile:
    settings = json.load(savfile)

MAX_WAV = settings["LASER"]["MAX_WAV"]
MIN_WAV = settings["LASER"]["MIN_WAV"]

__author__ = "Yves Auad"

class SirahCredoLaser:

    def __init__(self) -> None:
        self.abort_ctrl = False
        self.laser_thread = None
        self.thread = None
        self.lock = threading.Lock()

        self.ser = serial.Serial()
        self.ser.baudrate = 19200
        self.ser.port = 'COM12'
        self.ser.timeout = 0.2

        try:
            if not self.ser.is_open:
                self.ser.open()
                time.sleep(0.1)
                self.sucessfull = True
        except:
            print("***LASER***: Could not open serial port. Check if connected and port.")
            self.sucessfull = False

    def bytes_to_pos(self, s):
        dec_val = 0
        for i in range(len(s)):
            dec_val += 256 ** i * s[i]
        return dec_val

    def pos_to_bytes(self, pos):
        rem = pos
        val = numpy.zeros(4, dtype=int)
        for j in range(4):  # 4 bytes
            val[j] = rem % 256
            rem = rem - val[j]
            rem = rem / 256
        return val

    def pos_to_wl(self, pos):
        wl = -5.26094211e-17 * pos ** 3 + 8.28867083e-11 * pos ** 2 - 4.28775800e-4 * pos + 1.10796664e3
        return wl

    def wl_to_pos(self, wl):
        pos = -1.42336972e-4 * wl ** 3 - 8.58549626e-1 * wl ** 2 - 9.54738134e2 * wl + 2.16000371e6
        return int(pos)

    def set_hardware_wl(self, wl):
        pos = self.wl_to_pos(wl)
        byt = self.pos_to_bytes(pos)
        checksum = byt.sum() + 60 + 7 + 1  # head associated with send
        if (checksum > 255):
            checksum = checksum - 256 * int(checksum / 256)
        send_mes = [60, 7, 1, byt[0], byt[1], byt[2], byt[3], 0, 0, 0, 0, checksum, 62]
        ba_send_mes = bytearray(send_mes)
        pos2 = self.bytes_to_pos(byt)
        if (wl > MIN_WAV and wl < MAX_WAV):  # REMEMBER YOU WERE CALLED IN THE THREAD BELOW. YOU ARE WITH THE LOCKER!
            try:
                self.ser.write(ba_send_mes)
            except:
                print("***LASER***: Could not write in laser serial port. Check port.")

    def get_hardware_wl(self):
        mes = [60, 23, 0, 0, 0, 0, 0, 0, 0, 0, 0, 83, 62]
        bs = bytearray(mes)
        try:
            self.ser.write(bs)
            self.ser.read(1)
            error = self.ser.read(1)
            self.ser.read(1)
            status = self.ser.read(1)
            abs1 = self.ser.read(4)
            self.ser.read(6)  # clear buffer
            pos = self.bytes_to_pos(abs1)
            cur_wl = self.pos_to_wl(pos)
            if (status[0] == 2 or status[0] == 3):
                return (cur_wl, status[0])
            else:
                print('***LASER***: Status was not 02 or 03. Problem receiving bytes from laser hardware.')
                self.ser.close()
                time.sleep(0.05)
                self.ser.open()
                time.sleep(0.05)
                self.ser.write(bs)
                self.ser.read(1)
                error = self.ser.read(1)
                self.ser.read(1)
                status = self.ser.read(1)
                abs1 = self.ser.read(4)
                self.ser.read(6)  # clear buffer
                pos = self.bytes_to_pos(abs1)
                cur_wl = self.pos_to_wl(pos)
                return (cur_wl, status[0])
        except:
            print("***LASER***: Could not write/read in laser serial port. Check port.")
            return (580., None)

    def set_startWL(self, wl: float, cur: float):
        self.set_hardware_wl(wl)

    def setWL(self, wavelength: float, current_wavelength: float):
        if (abs(float(current_wavelength) - float(wavelength)) <= 0.001):
            return b'message_01'
        else:
            self.laser_thread = threading.Thread(target=self.set_startWL, args=(wavelength, current_wavelength,))
            self.laser_thread.start()
            return b'message_02'

    def abort_control(self):
        self.abort_ctrl = True

    def set_scan_thread_locked(self):
        return self.lock.locked()

    def set_scan_thread_release(self):
        if self.lock.locked():
            self.lock.release()

    def set_scan_thread_check(self):
        if self.thread == None:
            return True  # if there is none then its done
        else:
            return self.thread.done()

    def set_scan_thread_hardware_status(self):
        return self.get_hardware_wl()[1]  # 2 hold; 3 moving

    def set_scan_thread(self, cur, i_pts, step):
        if not self.abort_ctrl:
            self.lock.acquire()
            self.set_hardware_wl(cur + i_pts * step)
        else:
            with self.lock:
                print("Laser abort control function.")
                self.sendmessage(4)

    def set_scan(self, cur, step, pts):
        self.abort_ctrl = False
        pool = ThreadPoolExecutor(1)
        for index in range(pts):
            self.thread = pool.submit(self.set_scan_thread, cur, index, step)

