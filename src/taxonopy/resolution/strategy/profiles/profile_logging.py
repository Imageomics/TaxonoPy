import logging
import sys

# Use a unique attribute name to mark our specific handler
_OVERRIDE_HANDLER_ATTR = '_profile_debug_override_handler'

def setup_profile_logging(logger: logging.Logger, force_debug: bool):
    """
    Conditionally forces DEBUG level logging for a specific profile logger.

    Args:
        logger: The specific logger instance for the profile module.
        force_debug: If True, enable DEBUG logging for this logger regardless
                     of the global setting. If False, ensure override settings
                     are removed.
    """
    # Find existing override handler (if any)
    existing_override_handler = None
    for h in logger.handlers:
        if hasattr(h, _OVERRIDE_HANDLER_ATTR):
            existing_override_handler = h
            break

    if force_debug:
        # Enable override
        if existing_override_handler:
            # Handler already exists, ensure logger level is still DEBUG
            # This handles cases like module reloads
            if logger.level > logging.DEBUG or logger.level == logging.NOTSET:
                 logger.setLevel(logging.DEBUG)
            logger.debug(f"DEBUG logging override remains active for logger: {logger.name}")
        else:
            # Create and add the override handler
            override_handler = logging.StreamHandler(sys.stdout)
            override_handler.setLevel(logging.DEBUG) # Process DEBUG messages

            # Distinct formatter for easy identification
            formatter = logging.Formatter(f'%(asctime)s [%(levelname)s][DBG_OVERRIDE:{logger.name}] %(message)s')
            override_handler.setFormatter(formatter)

            # Mark the handler
            setattr(override_handler, _OVERRIDE_HANDLER_ATTR, True)

            logger.addHandler(override_handler)
            # Prevent messages from flowing to root handlers to avoid duplication
            # and respect the override isolation.
            logger.propagate = False
            # Set the logger level itself to DEBUG
            logger.setLevel(logging.DEBUG)
            logger.debug(f"DEBUG logging override ACTIVATED for logger: {logger.name}")

    else:
        # Disable override
        if existing_override_handler:
            logger.debug(f"DEBUG logging override DEACTIVATED for logger: {logger.name}")
            # Remove the handler
            logger.removeHandler(existing_override_handler)
            # Allow propagation to root handlers again
            logger.propagate = True
            # Reset logger level to inherit from parent/root
            # (Or specifically from global config if needed, but NOTSET is safer)
            logger.setLevel(logging.NOTSET)
        # If no override handler exists, do nothing when force_debug is False
