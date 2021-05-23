class Playlist {
    constructor(type, useri) {
        this.rowid = null;
        this.type = type;
        this.conf = {
            playlists: []
        };
        this.name = '';
        this.dateupdate = 0;
        this.autoupdate = 0;
        this.useri = useri;
    }
}