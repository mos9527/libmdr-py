"""ctypes structs and prototypes for the mdr-c ABI."""

from __future__ import annotations

from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    c_char,
    c_char_p,
    c_int,
    c_int8,
    c_uint32,
    c_uint8,
    c_void_p,
)

from . import _dll

UInt32 = c_uint32
MDRResult = c_uint32
MDRBoolean = c_uint32
MDREvent = c_uint32
MDRFeature = c_uint32
MDRFeatureAvailability = c_uint32
MDRText = c_uint32
MDRPacketDirection = c_uint32


class MDRDeviceInfo(Structure):
    _fields_ = [
        ("szDeviceName", c_char * 128),
        ("szDeviceMacAddress", c_char * 18),
    ]


class MDRConnection(Structure):
    pass


MDRConnectionConnect = CFUNCTYPE(MDRResult, c_void_p, c_char_p, c_char_p)
MDRConnectionDisconnect = CFUNCTYPE(None, c_void_p)
MDRConnectionRecv = CFUNCTYPE(MDRResult, c_void_p, c_char_p, c_int, POINTER(c_int))
MDRConnectionSend = CFUNCTYPE(MDRResult, c_void_p, c_char_p, c_int, POINTER(c_int))
MDRConnectionPoll = CFUNCTYPE(MDRResult, c_void_p, c_int)
MDRConnectionGetDevicesList = CFUNCTYPE(
    MDRResult, c_void_p, POINTER(POINTER(MDRDeviceInfo)), POINTER(c_int)
)
MDRConnectionFreeDevicesList = CFUNCTYPE(MDRResult, c_void_p, POINTER(POINTER(MDRDeviceInfo)))
MDRConnectionGetLastError = CFUNCTYPE(c_char_p, c_void_p)

MDRConnection._fields_ = [
    ("user", c_void_p),
    ("connect", MDRConnectionConnect),
    ("disconnect", MDRConnectionDisconnect),
    ("recv", MDRConnectionRecv),
    ("send", MDRConnectionSend),
    ("poll", MDRConnectionPoll),
    ("getDevicesList", MDRConnectionGetDevicesList),
    ("freeDevicesList", MDRConnectionFreeDevicesList),
    ("getLastError", MDRConnectionGetLastError),
]


class MDRModel(Structure):
    _fields_ = [
        ("protocol_version", c_uint32),
        ("audio_codec", c_uint32),
        ("model_color", c_uint8),
    ]


class MDRBattery(Structure):
    _fields_ = [
        ("part", c_uint32),
        ("present", MDRBoolean),
        ("level_percent", c_uint8),
        ("update_threshold_percent", c_uint8),
        ("charging", c_uint32),
    ]


class MDRPlayback(Structure):
    _fields_ = [
        ("status", c_uint32),
        ("volume", c_uint8),
    ]


class MDRPlaybackCommand(Structure):
    _fields_ = [
        ("action", c_uint32),
    ]


class MDRNoiseControl(Structure):
    _fields_ = [
        ("mode", c_uint32),
        ("ambient_level", c_uint8),
        ("focus_on_voice", MDRBoolean),
        ("button_mode", c_uint32),
        ("adaptive_ambient", MDRBoolean),
        ("adaptive_sensitivity", c_uint32),
    ]


class MDRSpeakToChat(Structure):
    _fields_ = [
        ("enabled", MDRBoolean),
        ("sensitivity", c_uint32),
        ("timeout", c_uint32),
    ]


class MDRListening(Structure):
    _fields_ = [
        ("mode", c_uint32),
        ("background_room", c_uint32),
    ]


class MDREqualizer(Structure):
    _fields_ = [
        ("preset", c_uint32),
        ("clear_bass", c_int8),
        ("band_count", c_uint32),
        ("dsee_enabled", MDRBoolean),
        ("dsee_type", c_uint32),
    ]


class MDRPairedDevice(Structure):
    _fields_ = [
        ("index", c_uint32),
        ("connected", MDRBoolean),
        ("playback_device", MDRBoolean),
    ]


class MDRPairedDeviceAction(Structure):
    _fields_ = [
        ("command", c_uint32),
        ("device_id", c_char_p),
        ("device_id_size", c_uint32),
    ]


class MDRPairing(Structure):
    _fields_ = [
        ("enabled", MDRBoolean),
    ]


class MDRGeneralSettingInfo(Structure):
    _fields_ = [
        ("index", c_uint32),
        ("type", c_uint32),
        ("writable", MDRBoolean),
    ]


class MDRGeneralSetting(Structure):
    _fields_ = [
        ("index", c_uint32),
        ("boolean_value", MDRBoolean),
    ]


class MDRAssignableControls(Structure):
    _fields_ = [
        ("left", c_uint32),
        ("right", c_uint32),
    ]


class MDRPower(Structure):
    _fields_ = [
        ("auto_power_off_minutes", c_uint32),
        ("wearing_power", c_uint32),
        ("auto_pause", MDRBoolean),
        ("head_gesture", MDRBoolean),
        ("shutdown_requested", MDRBoolean),
    ]


class MDRVoiceGuidance(Structure):
    _fields_ = [
        ("enabled", MDRBoolean),
        ("volume", c_int8),
    ]


class MDRConnectionMode(Structure):
    _fields_ = [
        ("audio_priority", c_uint32),
    ]


class MDRSafeListening(Structure):
    _fields_ = [
        ("sound_pressure", c_uint8),
        ("preview", MDRBoolean),
    ]


MDRPacketCallback = CFUNCTYPE(None, c_void_p, MDRPacketDirection, POINTER(c_uint8), c_int)


def _bind() -> None:
    lib = _dll.lib()

    lib.mdrResultString.argtypes = [MDRResult]
    lib.mdrResultString.restype = c_char_p

    lib.mdrConnectionConnect.argtypes = [POINTER(MDRConnection), c_char_p, c_char_p]
    lib.mdrConnectionConnect.restype = MDRResult
    lib.mdrConnectionDisconnect.argtypes = [POINTER(MDRConnection)]
    lib.mdrConnectionDisconnect.restype = None
    lib.mdrConnectionRecv.argtypes = [POINTER(MDRConnection), c_char_p, c_int, POINTER(c_int)]
    lib.mdrConnectionRecv.restype = MDRResult
    lib.mdrConnectionSend.argtypes = [POINTER(MDRConnection), c_char_p, c_int, POINTER(c_int)]
    lib.mdrConnectionSend.restype = MDRResult
    lib.mdrConnectionPoll.argtypes = [POINTER(MDRConnection), c_int]
    lib.mdrConnectionPoll.restype = MDRResult
    lib.mdrConnectionGetDevicesList.argtypes = [
        POINTER(MDRConnection),
        POINTER(POINTER(MDRDeviceInfo)),
        POINTER(c_int),
    ]
    lib.mdrConnectionGetDevicesList.restype = MDRResult
    lib.mdrConnectionFreeDevicesList.argtypes = [
        POINTER(MDRConnection),
        POINTER(POINTER(MDRDeviceInfo)),
    ]
    lib.mdrConnectionFreeDevicesList.restype = MDRResult
    lib.mdrConnectionGetLastError.argtypes = [POINTER(MDRConnection)]
    lib.mdrConnectionGetLastError.restype = c_char_p

    lib.mdrHeadphonesCreate.argtypes = [c_uint32, POINTER(MDRConnection), POINTER(c_void_p)]
    lib.mdrHeadphonesCreate.restype = MDRResult
    lib.mdrHeadphonesDestroy.argtypes = [c_void_p]
    lib.mdrHeadphonesDestroy.restype = None
    lib.mdrHeadphonesIsInitialized.argtypes = [c_void_p]
    lib.mdrHeadphonesIsInitialized.restype = MDRBoolean
    lib.mdrHeadphonesIsReady.argtypes = [c_void_p]
    lib.mdrHeadphonesIsReady.restype = MDRBoolean
    lib.mdrHeadphonesIsDirty.argtypes = [c_void_p]
    lib.mdrHeadphonesIsDirty.restype = MDRBoolean
    lib.mdrHeadphonesRequestInit.argtypes = [c_void_p]
    lib.mdrHeadphonesRequestInit.restype = MDRResult
    lib.mdrHeadphonesRequestFetch.argtypes = [c_void_p]
    lib.mdrHeadphonesRequestFetch.restype = MDRResult
    lib.mdrHeadphonesRequestCommit.argtypes = [c_void_p]
    lib.mdrHeadphonesRequestCommit.restype = MDRResult
    lib.mdrHeadphonesPoll.argtypes = [c_void_p, POINTER(MDREvent)]
    lib.mdrHeadphonesPoll.restype = MDRResult
    lib.mdrHeadphonesSetPacketCallback.argtypes = [c_void_p, MDRPacketCallback, c_void_p]
    lib.mdrHeadphonesSetPacketCallback.restype = None
    lib.mdrHeadphonesGetFeature.argtypes = [
        c_void_p,
        MDRFeature,
        POINTER(MDRFeatureAvailability),
    ]
    lib.mdrHeadphonesGetFeature.restype = MDRResult
    lib.mdrHeadphonesGetText.argtypes = [c_void_p, MDRText, c_uint32, c_char_p, POINTER(c_uint32)]
    lib.mdrHeadphonesGetText.restype = MDRResult
    lib.mdrHeadphonesGetModel.argtypes = [c_void_p, POINTER(MDRModel)]
    lib.mdrHeadphonesGetModel.restype = MDRResult
    lib.mdrHeadphonesGetBatteries.argtypes = [c_void_p, POINTER(MDRBattery), POINTER(c_uint32)]
    lib.mdrHeadphonesGetBatteries.restype = MDRResult
    lib.mdrHeadphonesGetPlayback.argtypes = [c_void_p, POINTER(MDRPlayback)]
    lib.mdrHeadphonesGetPlayback.restype = MDRResult
    lib.mdrHeadphonesSetPlayback.argtypes = [c_void_p, POINTER(MDRPlayback)]
    lib.mdrHeadphonesSetPlayback.restype = MDRResult
    lib.mdrHeadphonesPlayback.argtypes = [c_void_p, POINTER(MDRPlaybackCommand)]
    lib.mdrHeadphonesPlayback.restype = MDRResult
    lib.mdrHeadphonesGetNoiseControl.argtypes = [c_void_p, POINTER(MDRNoiseControl)]
    lib.mdrHeadphonesGetNoiseControl.restype = MDRResult
    lib.mdrHeadphonesSetNoiseControl.argtypes = [c_void_p, POINTER(MDRNoiseControl)]
    lib.mdrHeadphonesSetNoiseControl.restype = MDRResult
    lib.mdrHeadphonesGetSpeakToChat.argtypes = [c_void_p, POINTER(MDRSpeakToChat)]
    lib.mdrHeadphonesGetSpeakToChat.restype = MDRResult
    lib.mdrHeadphonesSetSpeakToChat.argtypes = [c_void_p, POINTER(MDRSpeakToChat)]
    lib.mdrHeadphonesSetSpeakToChat.restype = MDRResult
    lib.mdrHeadphonesGetListening.argtypes = [c_void_p, POINTER(MDRListening)]
    lib.mdrHeadphonesGetListening.restype = MDRResult
    lib.mdrHeadphonesSetListening.argtypes = [c_void_p, POINTER(MDRListening)]
    lib.mdrHeadphonesSetListening.restype = MDRResult
    lib.mdrHeadphonesGetEqualizer.argtypes = [c_void_p, POINTER(MDREqualizer)]
    lib.mdrHeadphonesGetEqualizer.restype = MDRResult
    lib.mdrHeadphonesSetEqualizer.argtypes = [c_void_p, POINTER(MDREqualizer)]
    lib.mdrHeadphonesSetEqualizer.restype = MDRResult
    lib.mdrHeadphonesGetEqualizerBands.argtypes = [c_void_p, POINTER(c_int8), POINTER(c_uint32)]
    lib.mdrHeadphonesGetEqualizerBands.restype = MDRResult
    lib.mdrHeadphonesSetEqualizerBands.argtypes = [c_void_p, POINTER(c_int8), c_uint32]
    lib.mdrHeadphonesSetEqualizerBands.restype = MDRResult
    lib.mdrHeadphonesGetPairedDevices.argtypes = [
        c_void_p,
        POINTER(MDRPairedDevice),
        POINTER(c_uint32),
    ]
    lib.mdrHeadphonesGetPairedDevices.restype = MDRResult
    lib.mdrHeadphonesSetPairedDevice.argtypes = [c_void_p, POINTER(MDRPairedDeviceAction)]
    lib.mdrHeadphonesSetPairedDevice.restype = MDRResult
    lib.mdrHeadphonesGetPairing.argtypes = [c_void_p, POINTER(MDRPairing)]
    lib.mdrHeadphonesGetPairing.restype = MDRResult
    lib.mdrHeadphonesSetPairing.argtypes = [c_void_p, POINTER(MDRPairing)]
    lib.mdrHeadphonesSetPairing.restype = MDRResult
    lib.mdrHeadphonesGetGeneralSettingInfo.argtypes = [
        c_void_p,
        POINTER(MDRGeneralSettingInfo),
        POINTER(c_uint32),
    ]
    lib.mdrHeadphonesGetGeneralSettingInfo.restype = MDRResult
    lib.mdrHeadphonesGetGeneralSetting.argtypes = [
        c_void_p,
        c_uint32,
        POINTER(MDRGeneralSetting),
    ]
    lib.mdrHeadphonesGetGeneralSetting.restype = MDRResult
    lib.mdrHeadphonesSetGeneralSetting.argtypes = [c_void_p, POINTER(MDRGeneralSetting)]
    lib.mdrHeadphonesSetGeneralSetting.restype = MDRResult
    lib.mdrHeadphonesGetAssignableControls.argtypes = [c_void_p, POINTER(MDRAssignableControls)]
    lib.mdrHeadphonesGetAssignableControls.restype = MDRResult
    lib.mdrHeadphonesSetAssignableControls.argtypes = [c_void_p, POINTER(MDRAssignableControls)]
    lib.mdrHeadphonesSetAssignableControls.restype = MDRResult
    lib.mdrHeadphonesGetPower.argtypes = [c_void_p, POINTER(MDRPower)]
    lib.mdrHeadphonesGetPower.restype = MDRResult
    lib.mdrHeadphonesSetPower.argtypes = [c_void_p, POINTER(MDRPower)]
    lib.mdrHeadphonesSetPower.restype = MDRResult
    lib.mdrHeadphonesGetVoiceGuidance.argtypes = [c_void_p, POINTER(MDRVoiceGuidance)]
    lib.mdrHeadphonesGetVoiceGuidance.restype = MDRResult
    lib.mdrHeadphonesSetVoiceGuidance.argtypes = [c_void_p, POINTER(MDRVoiceGuidance)]
    lib.mdrHeadphonesSetVoiceGuidance.restype = MDRResult
    lib.mdrHeadphonesGetConnectionMode.argtypes = [c_void_p, POINTER(MDRConnectionMode)]
    lib.mdrHeadphonesGetConnectionMode.restype = MDRResult
    lib.mdrHeadphonesSetConnectionMode.argtypes = [c_void_p, POINTER(MDRConnectionMode)]
    lib.mdrHeadphonesSetConnectionMode.restype = MDRResult
    lib.mdrHeadphonesGetSafeListening.argtypes = [c_void_p, POINTER(MDRSafeListening)]
    lib.mdrHeadphonesGetSafeListening.restype = MDRResult
    lib.mdrHeadphonesSetSafeListening.argtypes = [c_void_p, POINTER(MDRSafeListening)]
    lib.mdrHeadphonesSetSafeListening.restype = MDRResult


_bind()
