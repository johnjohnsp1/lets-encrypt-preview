"""Let's Encrypt Enhancement Display"""
import logging

import zope.component

from letsencrypt.client import errors
from letsencrypt.client import interfaces
from letsencrypt.client.display import util as display_util


def ask(enhancement):
    """Display the enhancement to the user.

    :param str enhancement: One of the
        :class:`letsencrypt.client.CONFIG.ENHANCEMENTS` enhancements

    :returns: True if feature is desired, False otherwise
    :rtype: bool

    :raises :class:`letsencrypt.client.errors.LetsEncryptClientError`: If
        the enhancement provided is not supported.

    """
    try:
        return dispatch[enhancement]()
    except KeyError:
        logging.error("Unsupported enhancement given to ask()")
        raise errors.LetsEncryptClientError("Unsupported Enhancement")


def redirect_by_default():
    """Determines whether the user would like to redirect to HTTPS.

    :returns: True if redirect is desired, False otherwise
    :rtype: bool

    """
    choices = [
        ("Easy", "Allow both HTTP and HTTPS access to these sites"),
        ("Secure", "Make all requests redirect to secure HTTPS access"),
    ]

    code, selection = util(interfaces.IDisplay).menu(
        "Please choose whether HTTPS access is required or optional.",
        choices)

    if code != display_util.OK:
        return False

    return selection == 1


util = zope.component.getUtility  # pylint: disable=invalid-name


dispatch = {  # pylint: disable=invalid-name
    "redirect": redirect_by_default
}