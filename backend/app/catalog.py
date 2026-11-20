from fastapi import HTTPException

from .db import write_transaction


def require_album(conn, album):
    if album is not None and not conn.execute("SELECT 1 FROM albums WHERE id=?", (album,)).fetchone():
        raise HTTPException(404, "Álbum no encontrado")


def album_clause(album, photo_id):
    if album is None:
        return "1", ()
    return f"{photo_id} IN (SELECT photo_id FROM album_photos WHERE album_id=?)", (album,)


ADD_TO_ALBUM = """INSERT INTO album_photos(album_id,photo_id)
    SELECT ?, id FROM photos WHERE id=? AND EXISTS(SELECT 1 FROM albums WHERE id=?)
    ON CONFLICT(album_id,photo_id) DO NOTHING"""


def attach_photo(conn, album, photo_id):
    if album is not None:
        conn.execute(ADD_TO_ALBUM, (album, photo_id, album))


def register_photo(conn, meta, name, album):
    # Inserting the catalogue row and assigning it to an album is one write.
    with write_transaction(conn):
        row = conn.execute(
            "INSERT INTO photos(sha256,original_name,ext,size,width,height,head_hash) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(sha256) DO NOTHING RETURNING id",
            (meta["sha256"], name, meta["ext"], meta["size"], meta["width"], meta["height"], meta["head"]),
        ).fetchone()
        photo_id = row["id"] if row else conn.execute(
            "SELECT id FROM photos WHERE sha256=?", (meta["sha256"],),
        ).fetchone()["id"]
        attach_photo(conn, album, photo_id)
    return photo_id, row is not None
