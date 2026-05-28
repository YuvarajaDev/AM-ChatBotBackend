"""
mcp_server/tools/milestone_config.py
=====================================
Python mirror of the frontend newMileStoneConfig.
Key = milestoneName from AM backend.
"""

MILESTONE_CONFIG = {
    "orderReceived": {
        "proceedMileStone": False,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [],
    },
    "bookingConfirm": {
        "proceedMileStone": False,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [],
    },
    "soRelease": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [],
    },
    "cargoRecievedCFS": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": True,
        "requiredFields": [
            {"type": "file", "label": "Upload File", "name": "cargoRecivedAtCFS", "isMultiFile": False, "fileLabel": "Cargo Received at CFS"},
        ],
    },
    "surveyCompleted": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": True,
        "instruction": (
            "Tell the user: 'The next milestone is Survey Completed.' "
            "Then ask ONLY: 'Before we proceed, does your shipment have any dimension deviations? (Yes / No)' — "
            "do not mention any files yet. Wait for the answer. "
            "If Yes: respond with 'If you have cargo deviations, please proceed with this milestone on AllMasters by filling in the cargo information.' "
            "Then STOP — do not ask for files, do not call update_milestone. "
            "If No: proceed to collect the requiredFields (file upload), confirm with the user, then call update_milestone."
        ),
        "requiredFields": [
            {"type": "file", "label": "Upload File", "name": "surveryCompleted", "isMultiFile": False, "fileLabel": "Survey Completed"},
        ],
    },
    "revisedMeasurment": {
        "proceedMileStone": False,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [],
    },
    "shippingBillUploaded": {
        "proceedMileStone": True,
        "isFloatingMileStone": True,
        "isFileUpload": True,
        "requiredFields": [
            {"type": "file", "label": "Upload File", "name": "shippingBill","isMultiFile": True},
            {"type": "text", "label": "Shipping Bill Number",   "name": "shippingBillNumber", "placeHolder": "Enter Shipping Bill Number"},
            {"type": "date", "label": "Shipping Bill Date",     "name": "shippingBillDate"},
        ],
    },
    "cargoDepartedICD": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [],
    },
    "cargoArrivedGateway": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [],
    },
    "containerSealno": {
        "proceedMileStone": False,
        "isFloatingMileStone": False,
        "shouldPerformAM": False,
        "isFileUpload": False,
        "requiredFields": [
            {"type": "text", "label": "Container Number", "name": "containerNo"},
            {"type": "text", "label": "Seal Number",      "name": "sealNo"},
        ],
    },
    "shippingInstruction": { # AI exstraction needed, hence need to perform threw AM portal
        "proceedMileStone": True,
        "isFloatingMileStone": True,
        "shouldPerformAM": True,
        "isFileUpload": True,
        "requiredFields": [
            {"type": "file", "label": "Upload File", "name": "shippingInstruction", "isMultiFile": False, "fileLabel": "Shipping Instruction"},
        ],
    },
    # AMSDetails has role-based sub-configs — handled in get_milestone_config()
    "AMSDetails": {
        "OT": {
            "proceedMileStone": True,
            "isFloatingMileStone": False,
            "isFileUpload": False,
            "requiredFields": [
                {"type": "text", "label": "HBL Number", "name": "forwarderHblNo", "placeHolder": "Enter HBL Number"},
            ],
        },
        "FF": {
            "proceedMileStone": True,
            "isFloatingMileStone": False,
            "isFileUpload": True,
            "requiredFields": [
                {"type": "checkbox", "label": "Upload AMS Manually", "name": "amsUpload"},
                {"type": "file",     "label": "Upload File",         "name": "amsDetails", "isMultiFile": False, "fileLabel": "AMS Details"},
            ],
        },
    },
    "ISFDetails": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": True,
        "requiredFields": [
            {"type": "file", "label": "Upload File", "name": "isfDetails", "isMultiFile": False, "fileLabel": "ISF Details"},
        ],
    },
    "AMSFilingCertificate": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": True,
        "requiredFields": [
            {"type": "file", "label": "Upload File", "name": "amdFilingCertificate", "isMultiFile": False, "fileLabel": "AMS Filing Certificate"},
        ],
    },
    "hblDraft": {
        "proceedMileStone": False,
        "isFloatingMileStone": False,
        "shouldPerformAM": True, # This is a special case — only proceed with this milestone via AM portal bcs it have doc genration, which is complex to handle in chat. So we set shouldPerformAM to True and tell user to proceed via AM portal.
        "isFileUpload": True,
        "requiredFields": [
            {"type": "file", "label": "Upload File", "name": "hblDraft", "isMultiFile": False, "fileLabel": "HBL Draft"},
        ],
    },
    "hblVerification": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": True,
        "requiredFields": [
            {"type": "file", "label": "Upload File", "name": "hblVerification", "isMultiFile": False, "fileLabel": "HBL Verification"},
        ],
    },
    "hblFinal": {
        "proceedMileStone": False,
        "isFloatingMileStone": True,
        "shouldPerformAM": True, # This is a special case — only proceed with this milestone via AM portal bcs it have doc genration, which is complex to handle in chat. So we set shouldPerformAM to True and tell user to proceed via AM portal.
        "isFileUpload": True,
        "requiredFields": [
            {"type": "text", "label": "HBL Number", "name": "hblNumber", "placeHolder": "Enter HBL Number"},
            {"type": "file", "label": "Upload File", "name": "hblFinal", "isMultiFile": False, "fileLabel": "HBL Final"},
        ],
    },
    "doRelease": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": True,
        "requiredFields": [
            {"type": "file", "label": "Upload File", "name": "doRelease", "isMultiFile": False, "fileLabel": "DO Release"},
        ],
    },
    "paymentRecieved": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [],
    },
    "stuffingReport": {
        "proceedMileStone": False,
        "isFloatingMileStone": False,
        "shouldPerformAM": True, # This is a special case — only proceed with this milestone via AM portal bcs it have doc genration, which is complex to handle in chat. So we set shouldPerformAM to True and tell user to proceed via AM portal.
        "isFileUpload": True,
        "requiredFields": [
            {"type": "file", "label": "Upload File", "name": "stuffingReport", "isMultiFile": False, "fileLabel": "Stuffing Report"},
        ],
    },
    "digitalCargoReceiptDraft": {
        "proceedMileStone": False,
        "isFloatingMileStone": False,
        "shouldPerformAM": True, # This is a special case — only proceed with this milestone via AM portal bcs it have doc genration, which is complex to handle in chat. So we set shouldPerformAM to True and tell user to proceed via AM portal.
        "isFileUpload": True,
        "requiredFields": [
            {"type": "text", "label": "Sea Waybill Number", "name": "seaWayBillNo", "placeHolder": "Enter Sea Waybill Number"},
            {"type": "file", "label": "Upload File", "name": "digitalCargoReceiptDraft", "isMultiFile": False, "fileLabel": "Digital Cargo Receipt Draft"},
        ],
    },
    "invoiceRelease": {
        "proceedMileStone": False,
        "isFloatingMileStone": False,
        "shouldPerformAM": True, # This is a special case — only proceed with this milestone via AM portal bcs it is handled by seprate logic, which is complex to handle in chat. So we set shouldPerformAM to True and tell user to proceed via AM portal.
        "isFileUpload": True,
        "requiredFields": [],
    },
    "paymentAdviceUpload": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": True,
        "requiredFields": [
            {"type": "file", "label": "Upload File", "name": "paymentAdvice", "isMultiFile": False, "fileLabel": "Payment Advice"},
        ],
    },
    "hblUploaded": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": True,
        "requiredFields": [
            {"type": "text", "label": "HBL Number", "name": "hblNumber", "placeHolder": "Enter HBL Number"},
            {"type": "file", "label": "Upload File", "name": "hbl",       "isMultiFile": False, "fileLabel": "HBL"},
        ],
    },
    "digitalCargoReceiptVerification": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "shouldPerformAM": True, # This is a special case — only proceed with this milestone via AM portal bcs it have doc genration, which is complex to handle in chat. So we set shouldPerformAM to True and tell user to proceed via AM portal.
        "isFileUpload": True,
        "requiredFields": [
            {"type": "file",     "label": "Upload File",       "name": "digitalCargoReceiptVerification", "isMultiFile": False, "fileLabel": "Digital Cargo Receipt Verification"},
            {"type": "checkbox", "label": "Terms & Conditions", "name": "termsCheck"},
        ],
    },
    "onboardConfirmation": {
        "proceedMileStone": False,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "shouldPerformAM": True, # This is a special case — only proceed with this milestone via AM portal bcs it is container management and have doc genration, which is complex to handle in chat. So we set shouldPerformAM to True and tell user to proceed via AM portal.
        "requiredFields": [
            {"type": "date", "label": "ATD",       "name": "atd"},
            {"type": "text", "label": "Port Name", "name": "portName"},
        ],
    },
    "digitalCargoReceiptFinal": {
        "proceedMileStone": False,
        "isFloatingMileStone": True,
        "shouldPerformAM": True, # This is a special case — only proceed with this milestone via AM portal bcs it have doc genration, which is complex to handle in chat. So we set shouldPerformAM to True and tell user to proceed via AM portal.
        "isFileUpload": True,
        "requiredFields": [
            {"type": "file", "label": "Upload File", "name": "digitalCargoReceiptFinal", "isMultiFile": False, "fileLabel": "Digital Cargo Receipt Final"},
        ],
    },
    "transhipment": {
        "proceedMileStone": False,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [
            {"type": "date", "label": "ATA",       "name": "aeta"},
            {"type": "text", "label": "Port Name", "name": "portName"},
        ],
    },
    "transhipmentDeparture": {
        "proceedMileStone": False,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [
            {"type": "date", "label": "ATD",    "name": "aetd"},
            {"type": "text", "label": "Vessel", "name": "vessel"},
            {"type": "text", "label": "Voyage", "name": "voyage"},
        ],
    },
    "can": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [
            {"type": "text", "label": "Marks & Numbers",        "name": "markNo",               "placeHolder": "Enter Marks & Numbers"},
            {"type": "text", "label": "Inland Transit Number",  "name": "inlandTransitNumber",   "placeHolder": "Enter Inland Transit Number"},
            {"type": "date", "label": "Inland Transit Date",    "name": "inlandTransitDate"},
        ],
    },
    "vesselArrived": {
        "proceedMileStone": False,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [
            {"type": "date", "label": "ATA",       "name": "ata"},
            {"type": "text", "label": "Port Name", "name": "portName"},
        ],
    },
    "cargoArrivedatDestinationHub": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [],
    },
    "destuffingCompleted": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [
            {"type": "date", "label": "Date", "name": "destuffingDate"},
        ],
    },
    "cargoPhotoUploaded": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": True,
        "requiredFields": [
            {"type": "file", "label": "Upload File", "name": "cargoPhotos", "isMultiFile": False, "fileLabel": "Cargo Photos"},
        ],
    },
    "eReleaseReady": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [],
    },
    "shipmentDepartedFinalDest": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [],
    },
    "shipmentarrivedFinalDest": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [],
    },
    "cargoAvailableForDelivery": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": True,
        "requiredFields": [
            {"type": "date", "label": "Date",        "name": "cargoDeliveryDate"},
            {"type": "file", "label": "Upload File", "name": "cargoAvialableForDelivery", "isMultiFile": False, "fileLabel": "Cargo Available for Delivery"},
        ],
    },
    "cargoGateOutConfirmed": {
        "proceedMileStone": True,
        "isFloatingMileStone": False,
        "isFileUpload": False,
        "requiredFields": [
            {"type": "dateAndTime", "label": "Date And Time", "name": "cargoGatewayDate"},
        ],
    },
}

def get_milestone_config(milestone_name: str, user_role: int = None) -> dict:
    """
    Return config for a milestone.
    Handles AMSDetails which has role-based sub-configs (OT vs FF).
    """
    cfg = MILESTONE_CONFIG.get(milestone_name)
    if cfg is None:
        return {}

    # AMSDetails: pick sub-config by role
    if milestone_name == "AMSDetails":
        if user_role == 5:   # OT
            return cfg["OT"]
        else:                # FF or others
            return cfg["FF"]

    return cfg


def should_perform_on_am(milestone_name: str, user_role: int = None) -> bool:
    """
    Returns True if shouldPerformOnAm flag is present and True in config.
    LLM should tell user to proceed via AllMasters portal for these milestones.
    """
    cfg = get_milestone_config(milestone_name, user_role)
    return cfg.get("shouldPerformOnAm", False) is True


def get_text_fields(milestone_name: str, user_role: int = None) -> list:
    """Return text/date/checkbox fields — validated by update_milestone. Excludes file and switch types."""
    cfg = get_milestone_config(milestone_name, user_role)
    return [f for f in cfg.get("requiredFields", []) if f["type"] not in ("file", "switch")]


def get_file_fields(milestone_name: str, user_role: int = None) -> list:
    """Return only file required fields — user uploads these in chat as base64."""
    cfg = get_milestone_config(milestone_name, user_role)
    return [f for f in cfg.get("requiredFields", []) if f["type"] == "file"]
