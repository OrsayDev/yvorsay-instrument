# standard libraries
import gettext
from nion.swift import Panel
from nion.swift import Workspace

from nion.ui import Declarative
from nion.ui import UserInterface
from nion.data import Calibration
from nion.data import DataAndMetadata
from nion.swift.model import HardwareSource
from nion.swift.model import DataItem
from nion.swift.model import Utility

from . import gain_inst
import numpy
import os
import json

_ = gettext.gettext

abs_path = os.path.abspath(os.path.join((__file__+"/../"), "global_settings.json"))
with open(abs_path) as savfile:
    settings = json.load(savfile)

MAX_CURRENT = settings["PS"]["MAX_CURRENT"]


class DataItemLaserCreation():
    def __init__(self, title, array, which):
        self.timezone=Utility.get_local_timezone()
        self.timezone_offset=Utility.TimezoneMinutesToStringConverter().convert(Utility.local_utcoffset_minutes())

        self.calibration=Calibration.Calibration()

        if which=='WAV':
            self.dimensional_calibrations=[Calibration.Calibration()]
            self.dimensional_calibrations[0].units='nm'
        if which=='POW':
            self.dimensional_calibrations=[Calibration.Calibration()]
            self.dimensional_calibrations[0].units='μm'
        if which=='SER':
            self.dimensional_calibrations=[Calibration.Calibration()]
            self.dimensional_calibrations[0].units='°'
        if which=='PS':
            self.dimensional_calibrations=[Calibration.Calibration()]
            self.dimensional_calibrations[0].units='A'
        if which=="CAM_DATA":
            self.dimensional_calibrations=[Calibration.Calibration(), Calibration.Calibration()]
            self.dimensional_calibrations[0].units='nm'
            self.dimensional_calibrations[1].units='eV'


        self.xdata=DataAndMetadata.new_data_and_metadata(array, self.calibration, self.dimensional_calibrations, timezone=self.timezone, timezone_offset=self.timezone_offset)

        self.data_item=DataItem.DataItem()
        self.data_item.set_xdata(self.xdata)
        self.data_item.define_property("title", title)
        self.data_item._enter_live_state()

    def update_data_only(self, array: numpy.array):
        self.xdata=DataAndMetadata.new_data_and_metadata(array, self.calibration, self.dimensional_calibrations, timezone=self.timezone, timezone_offset=self.timezone_offset)
        self.data_item.set_xdata(self.xdata)


class gainhandler:

    def __init__(self, instrument: gain_inst.gainDevice, document_controller):

        # self.event_loop=event_loop #MATHIEU
        self.event_loop = document_controller.event_loop
        self.document_controller = document_controller
        self.instrument = instrument
        self.enabled = False
        self.__camera_hardware = HardwareSource.HardwareSourceManager().hardware_sources[0]
        self.busy_event_listener = self.instrument.busy_event.listen(self.prepare_widget_disable)
        self.property_changed_event_listener = self.instrument.property_changed_event.listen(self.prepare_widget_enable)
        self.free_event_listener = self.instrument.free_event.listen(self.prepare_free_widget_enable)

        self.call_data_listener=self.instrument.call_data.listen(self.call_data)
        self.append_data_listener=self.instrument.append_data.listen(self.append_data)
        self.end_data_listener=self.instrument.end_data.listen(self.end_data)

        self.wav_di=None
        self.pow_di=None
        self.ser_di=None
        self.ps_di=None


        self.current_acquition = None

    def init_handler(self):
        self.event_loop.create_task(self.do_enable(False, ['init_pb']))  # not working as something is calling this guy

    def init_push(self, widget):
        self.instrument.init()
        self.init_pb.enabled = False
        self.event_loop.create_task(self.do_enable(True, ['init_pb']))  # not working as something is calling this guy

    def upt_push(self, widget):
        # self.grab()
        self.instrument.upt()

    def acq_push(self, widget):
        self.instrument.acq()

    def abt_push(self, widget):
        self.instrument.abt()

    def sht_push(self, widget):
        self.instrument.sht()

    def lock_push(self, widget):
        self.instrument.lock()

    def dio_check(self, widget, checked):
        self.instrument.diode(checked)

    def q_check(self, widget, checked):
        self.instrument.q(checked)

    def more_push(self, widget):
        self.instrument.more_cur()

    def less_push(self, widget):
        self.instrument.less_cur()

    def more_servo_push(self, widget):
        self.instrument.more_servo()

    def less_servo_push(self, widget):
        self.instrument.less_servo()

    async def do_enable(self, enabled=True, not_affected_widget_name_list=None):
        for var in self.__dict__:
            if var not in not_affected_widget_name_list:
                if isinstance(getattr(self, var), UserInterface.Widget):
                    widg = getattr(self, var)
                    setattr(widg, "enabled", enabled)

    def prepare_widget_enable(self, value):
        self.event_loop.create_task(self.do_enable(False, ["init_pb", "abt_pb"]))

    def prepare_widget_disable(self, value):
        self.event_loop.create_task(self.do_enable(False, ["init_pb"]))

    def prepare_free_widget_enable(self,
                                   value):  # THAT THE SECOND EVENT NEVER WORKS. WHAT IS THE DIF BETWEEN THE FIRST?
        self.event_loop.create_task(self.do_enable(True, ["init_pb"]))

    def call_data(self, nacq, pts, avg, start, end, ctrl):
        if self.current_acquition != nacq:
            self.current_acquition=nacq
            self.avg = avg
            self.start_wav=start
            self.end_wav=end
            self.ctrl=ctrl
            self.wav_array = numpy.zeros(pts*avg)
            self.pow_array = numpy.zeros(pts*avg)
            if self.ctrl==1: self.ser_array = numpy.zeros(pts*avg)
            if self.ctrl==2: self.ps_array = numpy.zeros(pts*avg)

            self.wav_di = DataItemLaserCreation("Laser Wavelength "+str(nacq), self.wav_array, "WAV")
            self.pow_di = DataItemLaserCreation("Power "+str(nacq), self.pow_array, "POW")
            if self.ctrl==1: self.ser_di = DataItemLaserCreation("Servo Angle "+str(nacq), self.ser_array, "SER")
            if self.ctrl==2: self.ps_di = DataItemLaserCreation("Power Supply "+str(nacq), self.ps_array, "PS")


            self.document_controller.document_model.append_data_item(self.wav_di.data_item)
            self.document_controller.document_model.append_data_item(self.pow_di.data_item)
            if self.ctrl==2: self.document_controller.document_model.append_data_item(self.ps_di.data_item)
            if self.ctrl==1: self.document_controller.document_model.append_data_item(self.ser_di.data_item)

            # CAMERA CALL
            self.cam_array = numpy.zeros((pts*avg, 1600))
            self.cam_di = DataItemLaserCreation('Gain Data '+str(nacq), self.cam_array, "CAM_DATA")
            self.document_controller.document_model.append_data_item(self.cam_di.data_item)



    def append_data(self, value, index1, index2, camera_data):

        try:
            cur_wav, power, control = value
        except:
            cur_wav, power = value

            self.wav_array[index2+index1*self.avg] = cur_wav
            self.pow_array[index2+index1*self.avg] = power
            self.cam_array[index2+index1*self.avg] = numpy.sum(camera_data.data, axis=0)
            if self.ctrl==1: self.ser_array[index2+index1*self.avg] = control
            if self.ctrl==2: self.ps_array[index2+index1*self.avg] = control

            self.wav_di.update_data_only(self.wav_array)
            self.pow_di.update_data_only(self.pow_array)
            self.cam_di.update_data_only(self.cam_array)
            if self.ctrl==1: self.ser_di.update_data_only(self.ser_array)
            if self.ctrl==2: self.ps_di.update_data_only(self.ps_array)

    def end_data(self):
        if self.wav_di: self.wav_di.data_item._exit_live_state()
        if self.pow_di: self.pow_di.data_item._exit_live_state()
        if self.ser_di: self.ser_di.data_item._exit_live_state()
        if self.ps_di: self.ps_di.data_item._exit_live_state()
        if self.cam_di: self.cam_di.data_item._exit_live_state()


class gainView:

    def __init__(self, instrument: gain_inst.gainDevice):
        ui = Declarative.DeclarativeUI()

        self.init_pb = ui.create_push_button(text="Init", name="init_pb", on_clicked="init_push")

        self.start_label = ui.create_label(text='Start Wavelength (nm): ')
        self.start_line = ui.create_line_edit(text="@binding(instrument.start_wav_f)", name="start_line")
        self.pts_label = ui.create_label(text='E-points: ')
        self.pts_value_label = ui.create_label(text="@binding(instrument.pts_f)")
        self.ui_view1 = ui.create_row(self.start_label, self.start_line, ui.create_stretch(), self.pts_label,
                                      self.pts_value_label, spacing=12)

        self.finish_label = ui.create_label(text='Finish Wavelength (nm): ')
        self.finish_line = ui.create_line_edit(text="@binding(instrument.finish_wav_f)", name="finish_line")
        self.tpts_label = ui.create_label(text='Total points: ')
        self.tpts_value_label = ui.create_label(text='@binding(instrument.tpts_f)')
        self.ui_view2 = ui.create_row(self.finish_label, self.finish_line, ui.create_stretch(), self.tpts_label,
                                      self.tpts_value_label, spacing=12)

        self.step_label = ui.create_label(text='Step Wavelength (nm): ')
        self.step_line = ui.create_line_edit(text="@binding(instrument.step_wav_f)", name="step_line")
        self.current_label = ui.create_label(text='Current Wavelength (nm): ')
        self.current_value_label = ui.create_label(text='@binding(instrument.cur_wav_f)')
        self.ui_view3 = ui.create_row(self.step_label, self.step_line, ui.create_stretch(), self.current_label,
                                      self.current_value_label, spacing=12)

        self.avg_label = ui.create_label(text='Averages: ')
        self.avg_line = ui.create_line_edit(text="@binding(instrument.avg_f)", name="avg_line")
        self.running_label = ui.create_label(text='Is running? ')
        self.running_value_label = ui.create_label(text='@binding(instrument.run_status_f)')
        self.ui_view4 = ui.create_row(self.avg_label, self.avg_line, ui.create_stretch(), self.running_label,
                                      self.running_value_label, spacing=12)

        self.dwell_label = ui.create_label(text='Dwell Time (ms): ')
        self.dwell_line = ui.create_line_edit(text="@binding(instrument.dwell_f)", name="dwell_line")
        self.ui_view5 = ui.create_row(self.dwell_label, self.dwell_line, ui.create_stretch(), spacing=12)

        self.upt_pb = ui.create_push_button(text="Update", name="upt_pb", on_clicked="upt_push")
        self.acq_pb = ui.create_push_button(text="Acquire", name="acq_pb", on_clicked="acq_push")
        self.abt_pb = ui.create_push_button(text="Abort", name="abt_pb", on_clicked="abt_push")
        self.ui_view6 = ui.create_row(self.upt_pb, self.acq_pb, self.abt_pb,
                                      spacing=12)  # yves: Note that i removed update button. It is useless

        self.power_label = ui.create_label(text='Power (uW): ')
        self.power_value_label = ui.create_label(text="@binding(instrument.power_f)")
        self.power_lock_button = ui.create_push_button(text='Lock', name='Lock_power', on_clicked='lock_push')
        self.power_lock_value = ui.create_label(text='@binding(instrument.locked_power_f)')
        self.ui_view7 = ui.create_row(self.power_label, self.power_value_label, self.power_lock_button,
                                      self.power_lock_value, ui.create_stretch(), spacing=12)

        self.line_label = ui.create_label(text='-', width=2)
        self.ui_view_line = ui.create_row(ui.create_stretch(), self.line_label, ui.create_stretch())

        self.diode_label = ui.create_label(text='Diodes: ')
        self.diode_checkbox = ui.create_check_box(name="diode_checkbox", on_checked_changed='dio_check')
        self.diode_value_label = ui.create_label(text="@binding(instrument.d_f)")
        self.q_label = ui.create_label(text='Q Switch: ')
        self.q_checkbox = ui.create_check_box(name="q_checkbox", on_checked_changed='q_check')
        self.q_value_label = ui.create_label(text='@binding(instrument.q_f)')
        self.control_label = ui.create_label(text="Control: ")
        self.control_list = ui.create_combo_box(items=['None', 'Servo', 'Laser PS'],
                                                current_index='@binding(instrument.pw_ctrl_type_f)',
                                                name='control_list')
        self.shutter_pb = ui.create_push_button(text='Shutter', name="sht_pb", on_clicked='sht_push')
        self.ui_view8 = ui.create_row(self.diode_label, self.diode_checkbox, self.diode_value_label,
                                      ui.create_stretch(), self.q_label, self.q_checkbox, self.q_value_label,
                                      ui.create_stretch(), self.control_label, self.control_list, ui.create_stretch(),
                                      self.shutter_pb, spacing=12)

        self.diode_cur_label = ui.create_label(text='Current 01: ')
        self.diode_cur_value_label = ui.create_label(text="@binding(instrument.cur_d1_f)")
        self.diode_cur2_label = ui.create_label(text='Current 02: ')
        self.diode_cur2_value_label = ui.create_label(text='@binding(instrument.cur_d2_f)')
        self.shutter_label02 = ui.create_label(text='Shutter: ')
        self.shutter_label02_value = ui.create_label(text='@binding(instrument.sht_f)')

        self.ui_view9 = ui.create_row(self.diode_cur_label, self.diode_cur_value_label, self.diode_cur2_label,
                                      self.diode_cur2_value_label, ui.create_stretch(), self.shutter_label02,
                                      self.shutter_label02_value, spacing=12)

        self.diode_cur_label = ui.create_label(text='Diode(1, 2) (A): ')
        self.diode_cur_slider = ui.create_slider(name="cur_slider", value='@binding(instrument.cur_d_f)', minimum=10,
                                                 maximum=int(MAX_CURRENT*100))
        self.text_label = ui.create_label(text='       ||       ')
        self.diode_cur_line = ui.create_line_edit(text='@binding(instrument.cur_d_edit_f)', name='cur_line')
        self.less_pb = ui.create_push_button(text="<<", name="less_pb", on_clicked="less_push", width=25)
        self.more_pb = ui.create_push_button(text=">>", name="more_pb", on_clicked="more_push", width=25)
        self.ui_view10 = ui.create_row(self.diode_cur_label, self.diode_cur_slider, self.text_label,
                                       self.diode_cur_line, ui.create_spacing(12), self.less_pb, ui.create_spacing(5),
                                       self.more_pb, ui.create_stretch())

        self.ascii_label = ui.create_label(text='@binding(instrument.ascii_f)')
        self.ui_view11 = ui.create_row(ui.create_stretch(), self.ascii_label, ui.create_stretch())

        self.servo_label = ui.create_label(text='Servo Motor: ')
        self.servo_slider = ui.create_slider(name="servo_slider", value='@binding(instrument.servo_f)', minimum=0,
                                             maximum=int(MAX_CURRENT)*100)
        self.less_servo_pb = ui.create_push_button(text="<<", name="less_servo_pb", on_clicked="less_servo_push",
                                                   width=25)
        self.more_servo_pb = ui.create_push_button(text=">>", name="more_servo_pb", on_clicked="more_servo_push",
                                                   width=25)
        self.ui_view12 = ui.create_row(self.servo_label, ui.create_spacing(12), self.servo_slider,
                                       ui.create_spacing(12), self.less_servo_pb, ui.create_spacing(5),
                                       self.more_servo_pb, ui.create_stretch())

        self.ui_view = ui.create_column(self.init_pb, self.ui_view1, self.ui_view2, self.ui_view3, self.ui_view4,
                                        self.ui_view5, self.ui_view6, self.ui_view7, self.ui_view_line, self.ui_view8,
                                        self.ui_view9, self.ui_view10, self.ui_view11, self.ui_view12, spacing=1)


def create_spectro_panel(document_controller, panel_id, properties):
    instrument = properties["instrument"]
    ui_handler = gainhandler(instrument, document_controller)
    ui_view = gainView(instrument)
    panel = Panel.Panel(document_controller, panel_id, properties)

    finishes = list()
    panel.widget = Declarative.construct(document_controller.ui, None, ui_view.ui_view, ui_handler, finishes)

    for finish in finishes:
        finish()
    if ui_handler and hasattr(ui_handler, "init_handler"):
        ui_handler.init_handler()
    return panel


def run(instrument: gain_inst.gainDevice) -> None:
    panel_id = "Laser"  # make sure it is unique, otherwise only one of the panel will be displayed
    name = _("Laser")
    Workspace.WorkspaceManager().register_panel(create_spectro_panel, panel_id, name, ["left", "right"], "left",
                                                {"instrument": instrument})
