"""Remove local paths and image history from new publication copies; audit files and ZIPs.

No source is overwritten. Geometry, animation and image pixel streams stay unchanged.
This checks machine-readable data, not names or faces visible in image pixels.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import zipfile

from PIL import Image

ABSOLUTE_PATH = re.compile(
    rb'(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]+(?!Windows[\\/]+Fonts[\\/])[^\x00\r\n"<>]{1,1024}|'
    rb'/(?:Users|home|tmp|mnt|media|Volumes)/[^\x00\r\n"<>]{1,1024})')
SECRET = re.compile(rb'(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|'
                    rb'github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|'
                    rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|'
                    rb'[?&](?:access_token|X-Amz-Signature)=[A-Za-z0-9%_-]{16,})')
PNG_PRIVATE = {b'tEXt', b'zTXt', b'iTXt', b'eXIf', b'tIME'}
USER_DIRECTORY = re.compile(rb'[A-Za-z]:[\\/]+Users[\\/]|/(?:Users|home)/', re.I)


def zstd():
    try:
        import zstandard
    except ImportError as exc:
        raise RuntimeError('Install kit requirements: zstandard is needed for compressed Blend files') from exc
    return zstandard


def blend_raw(data):
    if data.startswith(b'\x28\xb5\x2f\xfd'):
        with zstd().ZstdDecompressor().stream_reader(io.BytesIO(data)) as reader:
            data = reader.read()
    elif data.startswith(b'\x1f\x8b'):
        data = gzip.decompress(data)
    if not data.startswith(b'BLENDER'):
        raise ValueError('Unsupported Blend file encoding')
    return data


class BlendDocument:
    """Read Blender BHead/SDNA and Text lines without opening or executing a scene."""
    def __init__(self, raw):
        self.raw = raw
        self.endian = '<' if raw[8:9] == b'v' else '>'
        self.ptr = 8 if raw[7:8] == b'-' else 4
        self.blocks = []
        self.by_address = {}
        pos = 12
        header = 16 + self.ptr
        while pos + header <= len(raw):
            code = raw[pos:pos+4]
            size = self.number(pos+4, 'I')
            address = self.number(pos+8, 'Q' if self.ptr == 8 else 'I')
            dna, count = struct.unpack_from(self.endian+'II', raw, pos+8+self.ptr)
            block = {'code': code, 'address': address, 'dna': dna, 'count': count,
                     'start': pos+header, 'end': pos+header+size}
            if block['end'] > len(raw):
                raise ValueError('Truncated Blend block')
            self.blocks.append(block)
            self.by_address[address] = block
            pos = block['end']
            if code == b'ENDB':
                break
        if not self.blocks or self.blocks[-1]['code'] != b'ENDB':
            raise ValueError('Missing Blend end block')
        block = next(b for b in self.blocks if b['code'] == b'DNA1')
        dna = raw[block['start']:block['end']]
        pos = 4
        def strings(marker):
            nonlocal pos
            if dna[pos:pos+4] != marker:
                raise ValueError('Invalid SDNA section')
            pos += 4
            n = struct.unpack_from(self.endian+'I', dna, pos)[0]
            pos += 4
            values = []
            for _ in range(n):
                end = dna.index(0, pos)
                values.append(dna[pos:end].decode('ascii'))
                pos = end+1
            pos = (pos+3) & ~3
            return values
        self.names = strings(b'NAME')
        self.types = strings(b'TYPE')
        if dna[pos:pos+4] != b'TLEN':
            raise ValueError('Missing SDNA lengths')
        pos += 4
        self.sizes = struct.unpack_from(self.endian+'H'*len(self.types), dna, pos)
        pos = (pos+2*len(self.types)+3) & ~3
        if dna[pos:pos+4] != b'STRC':
            raise ValueError('Missing SDNA structures')
        pos += 4
        count = struct.unpack_from(self.endian+'I', dna, pos)[0]
        pos += 4
        self.structs = []
        for _ in range(count):
            typ, n = struct.unpack_from(self.endian+'HH', dna, pos)
            pos += 4
            fields, offset = {}, 0
            for _ in range(n):
                ft, fn = struct.unpack_from(self.endian+'HH', dna, pos)
                pos += 4
                name = self.names[fn]
                length = 1
                for dim in re.findall(r'\[(\d+)\]', name):
                    length *= int(dim)
                size = (self.ptr if '*' in name else self.sizes[ft])*length
                key = re.sub(r'\[.*', '', name).lstrip('*')
                fields[key] = (offset, size, self.types[ft], '*' in name)
                offset += size
            self.structs.append({'name': self.types[typ], 'fields': fields,
                                 'layout_valid': offset == self.sizes[typ]})
        self.by_type = {s['name']: s for s in self.structs}

    def number(self, pos, fmt):
        return struct.unpack_from(self.endian+fmt, self.raw, pos)[0]

    def field(self, name, key):
        schema = self.by_type[name]
        if not schema['layout_valid']:
            raise ValueError('Unsupported SDNA layout: '+name)
        return schema['fields'][key][0]

    def texts(self):
        result = {}
        pointer = 'Q' if self.ptr == 8 else 'I'
        for block in self.blocks:
            if not block['code'].startswith(b'TX'):
                continue
            start = block['start']
            offset = start+self.field('Text', 'id')+self.field('ID', 'name')
            end = self.raw.index(0, offset)
            name = self.raw[offset+2:end].decode('utf-8')
            pos = start+self.field('Text', 'lines')+self.field('ListBase', 'first')
            address = self.number(pos, pointer)
            lines, seen = [], set()
            while address:
                if address in seen:
                    raise ValueError('Cyclic Text lines')
                seen.add(address)
                line = self.by_address[address]['start']
                target = self.number(line+self.field('TextLine', 'line'), pointer)
                length = self.number(line+self.field('TextLine', 'len'), 'I')
                buf = self.by_address[target]
                if buf['start']+length > buf['end']:
                    raise ValueError('Truncated Text line')
                lines.append(self.raw[buf['start']:buf['start']+length].decode('utf-8'))
                address = self.number(line+self.field('TextLine', 'next'), pointer)
            result[name] = '\n'.join(lines)
        return result

    def path_locations(self):
        """Inspect actual C strings/char arrays, excluding numeric data and pointers."""
        for block in self.blocks:
            if block['dna'] >= len(self.structs) or block['code'] in (b'DNA1', b'ENDB'):
                continue
            schema = self.structs[block['dna']]
            body = self.raw[block['start']:block['end']]
            if schema['name'] == 'raw_data' and block['code'] == b'DATA':
                plain = body.split(b'\x00', 1)[0]
                if not plain or any(c < 32 and c not in (9, 10, 13) for c in plain):
                    continue
                try:
                    plain.decode('utf-8')
                except UnicodeDecodeError:
                    continue
                for match in ABSOLUTE_PATH.finditer(plain):
                    yield block['start']+match.start(), block['start']+match.end(), match.start() == 0, True
            elif schema['layout_valid'] and block['count'] == 1:
                for offset, size, typ, pointer in schema['fields'].values():
                    if typ != 'char' or pointer or size < 4:
                        continue
                    value = body[offset:offset+size].split(b'\x00', 1)[0]
                    for match in ABSOLUTE_PATH.finditer(value):
                        allowed = schema['name'] in ('FileSelectParams', 'LibraryWeakReference')
                        yield block['start']+offset+match.start(), block['start']+offset+match.end(), True, allowed


def sanitize_blend(data):
    raw = blend_raw(data)
    document = BlendDocument(raw)
    matches = list(document.path_locations())
    if SECRET.search(raw):
        raise ValueError('Credential-like content: review before publication')
    output = bytearray(raw)
    for start, end, clear, allowed in matches:
        if not allowed:
            raise ValueError('Path in external resource or unsupported field; resolve it before cleaning')
        if clear:
            replacement = b'\x00'*(end-start)
        else:
            # Fixed-width redaction inside Text lines keeps lengths and valid JSON/code.
            replacement = b' '*(end-start)
        output[start:end] = replacement
    output = bytes(output)
    if USER_DIRECTORY.search(output) or list(BlendDocument(output).path_locations()):
        raise ValueError('Private paths remain')
    metadata = {}
    for name, value in BlendDocument(output).texts().items():
        if name in ('asset.json', 'rig.json', 'body_preset.json'):
            metadata[name] = json.loads(value)
    return zstd().ZstdCompressor(level=9).compress(output), len(matches), metadata


def sanitize_png(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Invalid PNG')
    out, pos, removed, ended = bytearray(data[:8]), 8, 0, False
    while pos+12 <= len(data):
        size = struct.unpack_from('>I', data, pos)[0]
        end = pos+12+size
        if end > len(data):
            raise ValueError('Truncated PNG chunk')
        kind = data[pos+4:pos+8]
        if kind in PNG_PRIVATE:
            removed += 1
        else:
            out.extend(data[pos:end])
        pos = end
        if kind == b'IEND':
            ended = True
            break
    if not ended or pos != len(data):
        raise ValueError('Unexpected PNG trailing data')
    return bytes(out), removed


def sanitize_jpeg(data):
    if not data.startswith(b'\xff\xd8'):
        raise ValueError('Invalid JPEG')
    out, pos, removed = bytearray(data[:2]), 2, 0
    while pos < len(data):
        start = pos
        if data[pos] != 255:
            raise ValueError('Invalid JPEG marker')
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos >= len(data):raise ValueError('Truncated JPEG marker')
        marker = data[pos]
        pos += 1
        if marker in (0xDA, 0xD9):
            out.extend(data[start:])
            break
        if marker in range(0xD0, 0xD9) or marker == 0x01:
            out.extend(data[start:pos])
            continue
        if pos+2 > len(data):raise ValueError('Truncated JPEG segment')
        size = struct.unpack_from('>H', data, pos)[0]
        end = pos+size
        if size < 2 or end > len(data):
            raise ValueError('Truncated JPEG segment')
        if marker in (0xE1, 0xED, 0xFE):
            removed += 1
        else:
            out.extend(data[start:end])
        pos = end
    return bytes(out), removed


def clean_json(value):
    if isinstance(value, dict):
        return {k: clean_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_json(v) for v in value]
    if isinstance(value, str):
        encoded = value.encode('utf-8')
        if SECRET.search(encoded):
            raise ValueError('Credential-like JSON content')
        return ABSOLUTE_PATH.sub(b'[local path removed]', encoded).decode('utf-8')
    return value


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def clean_file(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists() or source.resolve() == destination.resolve():
        raise FileExistsError('Use a new destination')
    data = source.read_bytes()
    kind, metadata, removed = source.suffix.lower(), {}, 0
    if kind == '.blend':
        data, removed, metadata = sanitize_blend(data)
    elif kind == '.png':
        data, removed = sanitize_png(data)
    elif kind in ('.jpg', '.jpeg'):
        data, removed = sanitize_jpeg(data)
    elif kind == '.json':
        data = (json.dumps(clean_json(json.loads(data.decode('utf-8-sig'))), ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    elif kind == '.zip':
        raise ValueError('Clean extracted files and rebuild ZIPs; ZIP cleaning is not implicit')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return {'removed': removed, 'metadata': metadata}


def findings(data, suffix):
    if suffix == '.blend':
        data = blend_raw(data)
        result = ['absolute_path'] if USER_DIRECTORY.search(data) or list(BlendDocument(data).path_locations()) else []
        if SECRET.search(data):
            result.append('credential_pattern')
        return result
    elif suffix in ('.png', '.jpg', '.jpeg'):
        with Image.open(io.BytesIO(data)) as image:
            # Do not scan compressed pixel streams: they contain accidental matches.
            info = {k: str(v) for k, v in image.info.items() if k not in ('icc_profile', 'exif')}
            exif = {str(k): str(v) for k, v in image.getexif().items()}
            data = json.dumps({'info': info, 'exif': exif}).encode('utf-8')
            if any(k in image.info for k in ('exif', 'XML:com.adobe.xmp', 'comment')):
                return ['image_history_metadata'] + (['absolute_path'] if ABSOLUTE_PATH.search(data) else [])
            if any(k in info for k in ('File', 'Date', 'Time', 'Camera', 'Scene', 'RenderTime')):
                return ['image_history_metadata'] + (['absolute_path'] if ABSOLUTE_PATH.search(data) else [])
    result = []
    if ABSOLUTE_PATH.search(data):
        result.append('absolute_path')
    if SECRET.search(data):
        result.append('credential_pattern')
    return result


def audit_tree(root):
    root = Path(root).resolve()
    paths = [root] if root.is_file() else sorted(p for p in root.rglob('*') if p.is_file())
    issues, seen, checked = [], {}, 0
    def inspect(name, data, suffix):
        nonlocal checked
        key = hashlib.sha256(data).hexdigest()
        if key not in seen:
            seen[key] = findings(data, suffix)
        checked += 1
        if seen[key]:
            issues.append({'file': name, 'kinds': seen[key]})
    for path in paths:
        relative = path.name if root.is_file() else path.relative_to(root).as_posix()
        if path.suffix.lower() == '.zip':
            with zipfile.ZipFile(path) as archive:
                if archive.comment or any(i.comment or i.extra for i in archive.infolist()):
                    issues.append({'file': relative, 'kinds': ['unreviewed_zip_metadata']})
                for name in archive.namelist():
                    if not name.endswith('/'):
                        inspect(relative+'!'+name, archive.read(name), Path(name).suffix.lower())
        else:
            inspect(relative, path.read_bytes(), path.suffix.lower())
    return {'checked': checked, 'unique_contents': len(seen), 'issues': issues,
            'scope': 'local paths, image history metadata and common credential patterns; no pixel identity recognition'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('clean', 'check'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--input', type=Path, required=True)
        cmd.add_argument('--report', type=Path)
        if name == 'clean':
            cmd.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.input.resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if args.report and (args.report.exists() or args.report.resolve().is_relative_to(source)):
        raise ValueError('Use a new report path outside the input')
    if args.command == 'clean':
        destination = args.output.resolve()
        if destination.exists() or destination.is_relative_to(source) or source.is_relative_to(destination):
            raise ValueError('Use a new, separate output location')
        if args.report and args.report.resolve().is_relative_to(destination):
            raise ValueError('Keep the report outside publication output')
        paths = [source] if source.is_file() else sorted(p for p in source.rglob('*') if p.is_file())
        if source.is_dir():
            destination.mkdir(parents=True)
        for path in paths:
            target = destination if source.is_file() else destination/path.relative_to(source)
            clean_file(path, target)
        report = audit_tree(destination)
    else:
        report = audit_tree(source)
    if args.report:
        write_json(args.report, report)
    print(json.dumps({'checked': report['checked'], 'issues': len(report['issues'])}))
    if report['issues']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
