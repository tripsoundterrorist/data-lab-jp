"""Unconnected, explicit single-batch capture/save entry. No CLI or scheduler.

Default invocation touches neither credentials, API nor private storage. Live
execution needs all independent confirmations. No retries or publication path.
DPAPI protects the existing master key; the archive itself is not encrypted.
"""
from datetime import datetime, timezone
import hmac
from hashlib import sha256
from pathlib import Path

import revenue_mvp_fixed_scope_capture as capture
import revenue_mvp_fixed_scope_private_save as private_save
import revenue_mvp_archive_dpapi as protected

CONFIRMATION = 'RUN_ONE_FIXED_FIVE_CAPTURE_AND_NEW_PRIVATE_SAVE'
KEY_DOMAIN = b'DATA-LAB-fixed-five-price-image-subkey-v1'


def run(source, database, environment, output, *, expected_source_sha256,
        expected_database_sha256, batch_index=0, execute=False,
        confirmation=None, capture_confirmation=None, key_confirmation=None,
        save_confirmation=None):
    result = dict(status='BLOCKED', reason_code='EXPLICIT_CONFIRMATIONS_REQUIRED',
                  api_calls=0, key_read_attempted=False, key_read_performed=False,
                  write_attempted=False, output_written=False,
                  partial_file_may_exist=False, manual_review_required=False,
                  database_write_performed=False, publication_allowed=False)
    master = subkey = None
    save_attempted = False
    try:
        if (execute is not True or confirmation != CONFIRMATION
                or capture_confirmation != capture.confirmation_for(batch_index)
                or key_confirmation != protected.READ_CONFIRMATION
                or save_confirmation != private_save.CONFIRMATION):
            return result
        if (any(not isinstance(path,Path) for path in (source,database,environment))
                or not environment.is_file()
                or any(path.is_symlink() for path in (source,database,environment))
                or any(parent.is_symlink() for path in (source,database,environment) for parent in path.parents)):
            result['reason_code']='INPUT_BOUNDARY_INVALID'
            return result
        private_save._location(output, batch_index)
        if output.exists():
            result['reason_code']='EXISTING_OUTPUT_REFUSED'
            return result
        if (not capture.reader.bound(source, database, expected_source_sha256, expected_database_sha256)
                or not protected._acl_safe()):
            result['reason_code']='PREFLIGHT_UNCONFIRMED'
            return result
        result['key_read_attempted']=True
        master=protected.read_protected_key(confirmation=key_confirmation)
        if type(master) is not bytes or len(master)!=32:
            raise ValueError('KEY_INVALID')
        result['key_read_performed']=True
        # Memory-only, domain-separated subkey; never rotate or overwrite master.
        subkey=hmac.new(master,KEY_DOMAIN,'sha256').digest()
        del master
        master=None
        receipt,evidence=capture.capture(source,database,environment,
            expected_source_sha256=expected_source_sha256,
            expected_database_sha256=expected_database_sha256,batch_index=batch_index,
            execute=True,confirmation=capture_confirmation)
        result['api_calls']=receipt['api_calls']
        if evidence is None or receipt['status']!='FIVE_ITEM_CAPTURE_READY':
            result['reason_code']='CAPTURE_UNCONFIRMED_NO_SAVE'
            return result
        save_attempted=True
        saved=private_save.save(evidence,source.read_bytes(),output,
            expected_database_sha256=expected_database_sha256,batch_index=batch_index,
            authentication_key=subkey,evaluated_at=datetime.now(timezone.utc),
            confirmation=save_confirmation)
        # The capture count is not the save function's (zero) network count.
        result.update(saved)
        result.update(api_calls=receipt['api_calls'],key_read_attempted=True,key_read_performed=True)
        return result
    except Exception:
        result['reason_code']='CAPTURE_SAVE_FAILED_SAFE'
        if save_attempted:
            result.update(manual_review_required=True,partial_file_may_exist=True)
        return result
    finally:
        # Avoid retaining references. Python bytes do not guarantee memory erasure.
        del master,subkey
