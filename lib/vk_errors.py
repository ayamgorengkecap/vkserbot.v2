def get_error_description(error_code):
    errors = {
        5: "Authorization failed",
        6: "Too many requests per second",
        9: "Flood control",
        10: "Internal server error",
        14: "Captcha needed",
        15: "Access denied",
        18: "User was deleted or banned",
        100: "Invalid parameter",
        113: "Invalid user id",
        203: "Access to group denied",
    }
    return errors.get(error_code, f"Error {error_code}")

def is_skippable_error(error_code):
    return error_code in [15, 18, 203]

def is_rate_limit_error(error_code):
    return error_code in [6, 9]
