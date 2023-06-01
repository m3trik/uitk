# !/usr/bin/python
# coding=utf-8


class Example:
    """ """

    def __init__(self, *args, **kwargs):
        # super().__init__(*args, **kwargs)
        """ """
        self.sb = self.switchboard()

        # ctx = self.sb.animation.draggableHeader.ctx_menu
        # if not ctx.containsMenuItems:
        # 	ctx.add(self.sb.ComboBox, setObjectName='cmb000', setToolTip='')

        # ctx = self.sb.animation.tb000.ctx_menu
        # if not ctx.containsMenuItems:
        # 	ctx.add('QSpinBox', setPrefix='Frame: ', setObjectName='s000', set_limits='0-10000 step1', setValue=1, setToolTip='')
        # 	ctx.add('QCheckBox', setText='Relative', setObjectName='chk000', setChecked=True, setToolTip='')
        # 	ctx.add('QCheckBox', setText='Update', setObjectName='chk001', setChecked=True, setToolTip='')

        # ctx = self.sb.animation.tb001.ctx_menu
        # if not ctx.containsMenuItems:
        # 	ctx.add('QSpinBox', setPrefix='Time: ', setObjectName='s001', set_limits='0-10000 step1', setValue=1, setToolTip='The desired start time for the inverted keys.')
        # 	ctx.add('QCheckBox', setText='Relative', setObjectName='chk002', setChecked=False, setToolTip='Start time position as relative or absolute.')

    def draggableHeader(self, state=None):
        """ """
        dh = self.sb.example.draggableHeader

    def cmb000(self, state=None):
        """ """
        cmb = self.sb.example.cmb000

    def tb000(self, state=None):
        """ """
        tb = self.sb.example.tb000

    def b000(self, state=None):
        """ """
        b = self.sb.example.b000
        print(f"{b.name} signal: {b}\n{b.name} slot:   {self.b000}")
