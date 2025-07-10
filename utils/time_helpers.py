def convert_time_to_seconds(time_str: str) -> int:
    """
    Converts a time string in format "MM:SS" to total seconds.
    
    Args:
        time_str: Time string in format "MM:SS" (e.g., "12:34")
        
    Returns:
        Total seconds as integer
        
    Example:
        convert_time_to_seconds("12:34") returns 754
    """
    if not time_str or ':' not in time_str:
        return 0
    
    try:
        parts = time_str.split(':')
        if len(parts) != 2:
            return 0
        
        minutes = int(parts[0])
        seconds = int(parts[1])
        
        return minutes * 60 + seconds
    except (ValueError, IndexError):
        return 0