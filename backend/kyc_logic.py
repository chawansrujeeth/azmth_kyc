from kyc_fields import KYC_FIELDS

def create_empty_kyc():

    data = {}

    for field in KYC_FIELDS:
        data[field] = None

    return data


def get_next_missing_field(user_data):

    for field in KYC_FIELDS:

        if user_data[field] is None:
            return field

    return None