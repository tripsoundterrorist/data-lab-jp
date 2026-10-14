"""Explicit read-only bridge from protected Windows key storage to archive.

No key generation, rotation, plaintext file/console output or automatic loading.
Native DPAPI follows Microsoft's CryptUnprotectData contract (same entropy,
UI forbidden, clear native output before LocalFree).
"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess

import revenue_mvp_acquisition_archive as archive

KEY_PATH = Path('C:/Users/User/.data-lab-private/key-protection/archive-authentication-key.dpapi')
EVIDENCE_DIRECTORY = Path('C:/Users/User/.data-lab-private/acquisition-evidence')
ENTROPY = b'DATA-LAB-acquisition-archive-key-v1'
READ_CONFIRMATION = 'READ_PROTECTED_DATA_LAB_ARCHIVE_KEY'
POWERSHELL = 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'


def _acl_safe():
    # Fixed paths, no interpolation of archive data or user strings. Only a
    # boolean marker is returned; no key bytes or account identifier is emitted.
    script = """
    $ErrorActionPreference='Stop'
    $currentSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $sandboxSid=$null
    try{
      $sandboxAccount=[Security.Principal.NTAccount]::new($env:COMPUTERNAME,'CodexSandboxUsers')
      $sandboxSid=$sandboxAccount.Translate([Security.Principal.SecurityIdentifier]).Value
    }catch{}
    $readOnlyMask=[int][Security.AccessControl.FileSystemRights]'ReadAndExecute,Synchronize'
    $paths=@('C:\\Users\\User\\.data-lab-private',
    'C:\\Users\\User\\.data-lab-private\\acquisition-evidence',
    'C:\\Users\\User\\.data-lab-private\\key-protection',
    'C:\\Users\\User\\.data-lab-private\\key-protection\\archive-authentication-key.dpapi')
    foreach($path in $paths){
      if([IO.File]::Exists($path)){$acl=[IO.File]::GetAccessControl($path)}
      else{$acl=[IO.Directory]::GetAccessControl($path)}
      $rules=$acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])
      if(-not $acl.AreAccessRulesProtected -or $rules.Count -lt 2){throw 'ACL_INVALID'}
      if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $currentSid){throw 'OWNER_INVALID'}
      $seen=[Collections.Generic.HashSet[string]]::new()
      foreach($rule in $rules){
        $sid=$rule.IdentityReference.Value
        if($path -eq 'C:\\Users\\User\\.data-lab-private' -and $null -ne $sandboxSid -and $sid -eq $sandboxSid){
          if($rule.AccessControlType -ne 'Allow' -or (([int]$rule.FileSystemRights -band (-bnot $readOnlyMask)) -ne 0)){throw 'PARENT_SANDBOX_WRITE_OR_DENY_REFUSED'}
          continue
        }
        if($rule.AccessControlType -ne 'Allow' -or $sid -notin @($currentSid,'S-1-5-18')){throw 'ACL_INVALID'}
        [void]$seen.Add($sid)
      }
      if($seen.Count -ne 2){throw 'ACL_INVALID'}
    }
    Write-Output 'KEY_ACL_OK'
    """
    result=subprocess.run([POWERSHELL,'-NoProfile','-NonInteractive','-Command',script],
                          capture_output=True,timeout=15,check=False,
                          env={**os.environ,'PSModulePath':
                               'C:/Windows/System32/WindowsPowerShell/v1.0/Modules'})
    return result.returncode == 0 and result.stdout.strip() == b'KEY_ACL_OK'


def _unprotect(ciphertext):
    class Blob(ctypes.Structure):
        _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
    encrypted_buffer=(ctypes.c_ubyte*len(ciphertext)).from_buffer_copy(ciphertext)
    entropy_buffer=(ctypes.c_ubyte*len(ENTROPY)).from_buffer_copy(ENTROPY)
    encrypted=Blob(len(ciphertext),encrypted_buffer)
    entropy=Blob(len(ENTROPY),entropy_buffer)
    output=Blob()
    crypt=ctypes.WinDLL('C:/Windows/System32/Crypt32.dll',use_last_error=True)
    kernel=ctypes.WinDLL('C:/Windows/System32/Kernel32.dll',use_last_error=True)
    decrypt=crypt.CryptUnprotectData
    decrypt.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.POINTER(Blob),
                     ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    decrypt.restype=wintypes.BOOL
    kernel.LocalFree.argtypes=[ctypes.c_void_p]
    kernel.LocalFree.restype=ctypes.c_void_p
    try:
        if not decrypt(ctypes.byref(encrypted),None,ctypes.byref(entropy),None,None,1,ctypes.byref(output)):
            raise ValueError('DPAPI_KEY_UNAVAILABLE')
        if output.cbData != 32 or not output.pbData:
            raise ValueError('DPAPI_KEY_INVALID')
        return ctypes.string_at(output.pbData,output.cbData)
    finally:
        if output.pbData:
            ctypes.memset(output.pbData,0,output.cbData)
            kernel.LocalFree(output.pbData)


def read_protected_key(*, confirmation=None):
    if confirmation != READ_CONFIRMATION:
        raise ValueError('EXPLICIT_KEY_READ_REQUIRED')
    try:
        if (os.name != 'nt' or not KEY_PATH.is_file()
                or any(p.is_symlink() for p in (KEY_PATH,*KEY_PATH.parents))
                or not _acl_safe()):
            raise ValueError
        with KEY_PATH.open('rb') as handle:
            ciphertext=handle.read(16385)
        if not 0 < len(ciphertext) <= 16384:
            raise ValueError
        key=_unprotect(ciphertext)
        if type(key) is not bytes or len(key)!=32 or KEY_PATH.read_bytes()!=ciphertext or not _acl_safe():
            raise ValueError
        return key
    except Exception:
        raise ValueError('PROTECTED_ARCHIVE_KEY_UNAVAILABLE') from None


def _archive_location(path):
    if (not isinstance(path,Path) or not path.is_absolute()
            or path.parent.resolve() != EVIDENCE_DIRECTORY.resolve()
            or any(p.is_symlink() for p in (path,*path.parents))):
        raise ValueError('APPROVED_PRIVATE_ARCHIVE_LOCATION_REQUIRED')


def save_with_dpapi(evidence,source_bytes,candidate_bytes,output,*,confirmation=None,evaluated_at=None):
    if confirmation != archive.SAVE_CONFIRMATION:
        raise ValueError('EXPLICIT_PRIVATE_SAVE_CONFIRMATION_REQUIRED')
    _archive_location(output)
    key=read_protected_key(confirmation=READ_CONFIRMATION)
    try:
        return archive.save(evidence,source_bytes,candidate_bytes,output,
                            authentication_key=key,confirmation=confirmation,evaluated_at=evaluated_at)
    finally:
        del key


def load_with_dpapi(path,source_bytes,candidate_bytes,*,expected_archive_sha256,
                    expected_database_sha256,evaluated_at=None,confirmation=None):
    if confirmation != READ_CONFIRMATION:
        raise ValueError('EXPLICIT_KEY_READ_REQUIRED')
    _archive_location(path)
    key=read_protected_key(confirmation=confirmation)
    try:
        return archive.load(path,source_bytes,candidate_bytes,
            expected_archive_sha256=expected_archive_sha256,
            expected_database_sha256=expected_database_sha256,
            authentication_key=key,evaluated_at=evaluated_at)
    finally:
        del key
