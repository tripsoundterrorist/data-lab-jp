"""Explicit create-only save of owned five-item evidence. No key loading.

Authentication keys must be supplied through a separately approved channel.
No API calls, DPAPI decrypt, key generation, mkdir, overwrite, deletion, retries,
database writes, scheduler or publication. HMAC is not encryption.
"""
from hashlib import sha256
import os
from pathlib import Path
import re
import stat

import revenue_mvp_archive_dpapi as protected
import revenue_mvp_fixed_scope_capture as capture_format

EVIDENCE_DIRECTORY = protected.EVIDENCE_DIRECTORY
CONFIRMATION = 'SAVE_FIXED_FIVE_PRIVATE_NEW_ONLY'


def _location(output, batch_index):
    if (not isinstance(output, Path) or not output.is_absolute()
            or type(batch_index) is not int or not 0 <= batch_index < 20
            or not re.fullmatch(rf'fixed-five-b{batch_index:02d}-[0-9a-f]{{32}}\.json', output.name)
            or not EVIDENCE_DIRECTORY.is_dir()
            or output.parent.resolve() != EVIDENCE_DIRECTORY.resolve()):
        raise ValueError('PRIVATE_LOCATION_INVALID')
    for path in (output, *output.parents):
        if path.is_symlink():
            raise ValueError('REPARSE_POINT_REFUSED')
        try:
            attributes = path.lstat().st_file_attributes
        except FileNotFoundError:
            continue
        except AttributeError:
            attributes = 0
        if attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
            raise ValueError('REPARSE_POINT_REFUSED')


def _read_back(handle):
    handle.seek(0)
    return handle.read(capture_format.MAX_BYTES + 1)


def save(evidence, source_bytes, output, *, expected_database_sha256,
         batch_index, authentication_key, evaluated_at, confirmation=None):
    result = dict(status='BLOCKED', reason_code='EXPLICIT_SAVE_CONFIRMATION_REQUIRED',
                  write_attempted=False, output_written=False,
                  partial_file_may_exist=False, manual_review_required=False,
                  key_read_performed=False, api_calls=0,
                  database_write_performed=False, publication_allowed=False)
    if confirmation != CONFIRMATION:
        return result
    created = False
    try:
        _location(output, batch_index)
        if output.exists():
            result['reason_code'] = 'EXISTING_OUTPUT_REFUSED'
            return result
        if not protected._acl_safe():
            result['reason_code'] = 'PROTECTED_LOCATION_UNCONFIRMED'
            return result
        args = dict(expected_database_sha256=expected_database_sha256,
                    batch_index=batch_index, authentication_key=authentication_key,
                    evaluated_at=evaluated_at)
        data = capture_format.encode(evidence, source_bytes, **args)
        if len(data) > capture_format.MAX_BYTES:
            raise ValueError('ARCHIVE_TOO_LARGE')
        if capture_format.verify(data, source_bytes, **args)['status'] != 'AUTHENTICATED_FORMAT_VERIFIED':
            raise ValueError('PREWRITE_VERIFICATION_FAILED')
        # Repeat boundary checks immediately before exclusive creation.
        _location(output, batch_index)
        if not protected._acl_safe():
            raise ValueError('PROTECTED_LOCATION_CHANGED')
        with output.open('x+b') as handle:
            created = True
            result['write_attempted'] = True
            if handle.write(data) != len(data):
                raise ValueError('SHORT_WRITE')
            handle.flush()
            os.fsync(handle.fileno())
            observed = _read_back(handle)
            _location(output, batch_index)
            disk_stat = output.stat(follow_symlinks=False)
            handle_stat = os.fstat(handle.fileno())
            if (observed != data or disk_stat.st_ino != handle_stat.st_ino
                    or disk_stat.st_dev != handle_stat.st_dev
                    or not protected._acl_safe()
                    or capture_format.verify(observed, source_bytes, **args)['status'] != 'AUTHENTICATED_FORMAT_VERIFIED'):
                raise ValueError('WRITE_VERIFICATION_FAILED')
        result.update(status='PRIVATE_FIXED_FIVE_ARCHIVE_SAVED',
                      reason_code='NO_DATABASE_OR_PUBLICATION_AUTHORITY',
                      output_written=True, archive_sha256=sha256(data).hexdigest(),
                      record_count=5)
        return result
    except FileExistsError:
        result['reason_code'] = 'EXISTING_OUTPUT_REFUSED'
    except Exception:
        result['reason_code'] = 'PRIVATE_SAVE_FAILED_SAFE'
    if created:
        result.update(partial_file_may_exist=True, manual_review_required=True)
    return result
