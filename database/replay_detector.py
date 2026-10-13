import hashlib
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "trackguard.db")
DB_NAME = DB_PATH


def create_fingerprint(imei, protocol, packet_type, packet_data):
    """
    Creates a unique fingerprint for a packet.
    """

    data = (
        imei
        + protocol
        + packet_type
        + packet_data
    )

    return hashlib.sha256(data.encode()).hexdigest()


def is_replay(fingerprint):
    """
    Checks whether this packet fingerprint
    has already been processed.
    """

    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    cursor.execute("""
    SELECT COUNT(*)
    FROM packet_fingerprints
    WHERE fingerprint = ?
    """, (fingerprint,))

    count = cursor.fetchone()[0]

    connection.close()

    return count > 0


def store_fingerprint(fingerprint, imei):
    """
    Stores a new packet fingerprint.
    """

    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO packet_fingerprints
    (fingerprint, imei)
    VALUES (?, ?)
    """, (fingerprint, imei))

    connection.commit()
    connection.close()