"""Open only the pinned I-39 publisher using the existing owner CMS ingress."""

import base64
import gzip
from hashlib import sha256
import io
import os
from pathlib import Path
import re
import stat
import subprocess


KEY_DIR = Path('/root/nox/state/owner-wow-ingress-7015017904')
CERT_SHA = '9788202aecc431b4e1a92beb6790d7cea75f6f3dfccbebc373f029b33ee4f6d2'
CIPHER_SHA = '529123e3d69616971ccf53895ac9e17aff33a895862aa63b76c9f6fe9a5ea6f8'
PACKET_SHA = '3640dcba4a816bf0767264321b484866840c8fe4a44d42bdf3d75b0c671444f6'
ENTRY_SHA = '4c4b836e7a6ff92674e4d623269c0fe6cbb995e0a85c0e7b2b59c5fcb2bc29d5'
CIPHER_B64 = 'MIIXcgYJKoZIhvcNAQcDoIIXYzCCF18CAQAxggFWMIIBUgIBADA6MCIxIDAeBgNVBAMMF05PWC1XT1ctT3duZXItVHJhbnNwb3J0AhRtfsoanyyal8t/DVPfRqWE7K4fRzANBgkqhkiG9w0BAQEFAASCAQBtHdS0YbIHfqGkA9BCmh2hLPc2t3nrBFxruKbAK1L80M9e5mhBz0+651y+O9Fz/PvHRgcOFEZsHeorG8mOa3z2giF1Qa2l/jG8zqMkrCT5jqyHmZGe9xKHMpeaiWqwsAh992cMYuqJfzaRZFRYFwaG8SG1oNFTsZN5O16XNQRVnQ86pYrPtYGQXHIxt0iiYcBjhxsvPeo8kmFXFi7Q06UgaOJYtlu8nV3La+tVxOegwqxxtyAmm3rAWVG5zIdJckMyznD/WmPEpS//l1mPdNSAuKYQ6HECvPAjcHOJ/7rPLeUIQ9zVIaZk+77JlB/HOeWasjrLuKgjVUSGpfUIEpUOMIIV/gYJKoZIhvcNAQcBMB0GCWCGSAFlAwQBKgQQYMR7/ndTfuGams9ICJfxN4CCFdDRO0zgJrdPCq/K1ts4vnC95Cq2CgudIPagBU+KQSh7Zs0SzMO/V29znnuOzqv6ECBAdA2k4IiekfzwulUHGPqRc7Oe0niftfO+0ZW8aDdagio4SBS5xGCsynaiQXs3H1g/TJfuskUuZeF27vkBcpxtYM9Ahq4QxQq7BJTIkrktW7NWCNeizGicLd/rSIt7n64uazc0jBWeDKn53MB5L5uWWsWGVgVsysaqipjIhUiOBJTo0zFOhvMAEybq/lC5O8gAqcetH5FpDU/RJAJ0A3ReaaRaBEkJMjiYHooht7AGC7ymnuS+kMCD1/AF6QA/Huq28t7X6mVRDgN8HEUOMPkybGC3JEgOZ+kDh4EfC3fCpEp8jInYi8ILMayYhEM5ZwR3RwO7ChoeREz8fvEGhvYsOz36uOn1rnHBiNcLj3wJDs1ZfdM70XJtU48OkDoomipPvGCnVM9Pr3ClM3pRWgXVl0+C6Bm1DQzsAI1F3m+3o+cyeC4UBMf3M4iFHoZGhKCU0D+mWmsflFJbK0I2nkDNhx4OPtuAqK2JC+9Ge6Xyhjvsy6lkIzdfZ/1n9WWH4hcGPoqbKc17xZGOX9aPUi1GOsoH1mchMB4IMzUjvx3XH9OSFsHZUC2zgjpP3vK31NWqyBBzwbsRB2V74llE5zLg8Eli7w/AeZ3qDaZnciRr8XMRJEvKQI7f7QsLNbmlbOYYA1N0xs/XvaiOcoJzpwL0HN6+Su3+OgNZxoSJruxmUELKI4Y0FzI1eU4RV65huMA/ipzgVNfTp1BBCFnZ05dsB4a7As/rSEX/gIc6xIr0KilQXeIfO0whJik1m/yM/8bVQgiu2hhtIrtepOuhDkFvZhVTUovehcLph8BAMd0AQ1+f4bPYhLfihAU98HKMnl6zz1RekpLfZOW+y4EcshgFov+iKBkzgihIhVTb3T2IsBLbNwEiHXhl1Rz3Q/JA9TkGJOh/vWNHKm2I84koGC1gf3q/3JCVotxLkDND/xDOtu0LDHCikEFoMmY1ly9BGit5DmbO30vAzj6elrJm7eJGAfw833IZed6ZuiPSvBDGHMhY/uKG/RuznYopNgJMJe3iUJ70FYN5l5MRX+7m6hTVKiUfdhRElkLbTGFlf+n2wCAdghZe6UOfxxxtaFZTtohfJxIWKKRokNZC6z0Jc9f2YmRtAqbLgp1lUdESNcBPIPOhXJknekIGArpSrxFZngEioa69zlKTDZktw4N6C3Etv5ooLzAofPgh/4fyz8Hirl/QA0s9m1ND/uFiEKUMsS/M85VAWmQBiaKgT7H93PFlbRjDkVuzmhJstt2rPrIzyQVf5Pjg0cGUuXflcdWKLpQtMEafIgvuFdsOY9vFCIkvOJIZJMhPRKljnzhtHVSM2fBCJEqd9+PW+0UdHPH53gnJ4pNyaA/3fCYPQr1y4O53QjTnmZpVsZoDhSHhql8rQmM6WB4uSZBkgbr9BRSgm631LUtS/kJqvMrpXDVlw0CiCulkmeNmXIMkzi7dvv+E52F/+otBClct+ZpclC1ygzGtlTtW/Ik3iAXqengkRQGHu0VJfJX+Xicy+QyUriOSeyOU0nDLdEmDXkXsyftrHPnRyKNDadAXnZpLHeJnIVEURi4tP+WzhKbJxy/EM9vjLMQa/DlAeqR/1443YXzWsbi43d8csfXQ6isquUmTtuuYrqsBWHqu1I8poiDREY9uKQHKYQciyspPL+E3AVqmfEQvhVw0NvcsAsYptanXI1eWIbtSxOgYYjQSaVTEc+AMomJgZ4oYKLzewqe0frgHJWWTyTd0ySaViEhtMSqgNjBR0Xp7NP+3qF2/aGfGFu+zXSycFruq+F3IhpUqdjW0OwD+pSWAiN1w+Z9vkhsGefey/R/q4+UHRfyVcL3f1NhNkLLmDwGvwlLeoJ5HcrHe+pNBoVO+22iMniWkmvb6kABokO1XKlNDf75HTXRhVhQ9SM1nXcZN8zH7Gn+cbYeprCLdAY7VExSqV2sHfSlluWIJ7OS3hot5SWiFIY8gyv0q2UMeX2zYPs2bV8YOsdSGOt1JGxZpsqATHMaxsPko28wxGRihSanW3GJdh27fzzLxTKp+sSolS/JiFCx8k2s6e6I2+3yoV1ESMgamNwR2sBVvJa+4m94z9GJ/MWyuxWkO02t85hci4BtCVLuWmVMHJnmF8bFIxlUfVZCD7aPMdrn7vW1X/BBzm5C/eZxlf1Xz7UomvGh6iAx3bBCKl5hrS3utLswYFSgXQjOkFCnzLR6fmZ6avr7yaJgoaQmdkvS7AAbgCkU9nx2YGTV8cBLJbMHKIx0vSOkDnJ1XAILM4cVYzUl6SQwMpTiU6G/yJ68HKI9MqM2+RVYJXgTFxiyCBv6EMNfdu+a23N96nKqFySaifxhwoeT7GQpqCLdn6hLMYyXOgoi/6p/+06rYPboa36QTNSk8X3QyteEVu8/WywvHzcaBMCMpQ7waJP/Q8drPGr1ssnECGI8I8jLADH4R4UYwI8ZXa/XuISpCOucwHt5qaijz0mpt28p27wYs19S9N30AMtPc2j6psdnzkyPUs/1osZDLYDKnOCOPNWk+vuoPscdB1hXxAuHjblxssuik5camKOkI/4LYW9GV5q0xAmvQPuRoRngu2K0ZgRRSROOQDTj9swEfbMYfNFFXhPjjWIYnBhK3Bg7VY1TZRLdUeh2OPiGtUnTp927ZODwZANvqj0sNycMbpEAkri286T946wR/RZgk9XQxoHL4omMsemOgbiVtD2h1rcHYYpEJidTUypaoowDH7KJCtFm4MnbDqfg8vevfDudYX/tnnCD4uVDdOZcVEYNLDs85gdwTyY6qIJKphxkvDkLPq4awgRxoSlToFgci1wlIgEBi5QVkIudMDwpaS+ig7YpGZmjenP6eFKbcQY6y8m1CVVEKBB+nF+AS3giiA6tv9wdWr6zdCOoXqBNlRVTkzH7e6VhicM69AJcYnYpFXYpdcZDZTdP6Jc0SMr2jNpogfogBjCP6WDqO0r36YYcWwSdgSvjZ8ZAyOcfWFBKhyfEoj5bpitu2RiF5TsBgTnbnckqxKzey6HO3W8fqvL1WobNan93RGB6PwtCT5KtANgcvBO06eMrovg9lVdXMJ8CH1VomQiZ8DoYA4jzePJ6KK44K+TvKQEx88dIkLEQw6Rlcu2ZpOQMS0jH4BG/MmKqW43KNQKHK14qqDOd8dBbe5Dpevx9XHUgZVB3NJEaW0fp8wkDJsXJ8kadPqF7fAUNQKLchnYZJ2foCARODNxuSEHuP4lVUayJx1sqwQ+Nl9lgF6oZTJcevPGx2OPVheNbDCv00as6cROq8PVBPZYE33v213dTGq/qVZXy9Wm1E8XKsdXMoBaQKGyOqRogXJxyxkmKXFC75Ili3SUSc/U5x7lfEijypQgKhoqNKD3l4Jv856q7Fo3XWy4lw6IkvTWeFXZVjgeLCvzuVoV5EmNI1jQUQYJqecB4OFe/BIlYFiqg2rb+Qfb0Z3/yK0ToaUiI6v8hcSNPLaBIwLTzZRNSEdz9ZMZhQ6t61XKWd38inh9k0kdqslElTBbuMqgql50Kiac/IWd+Wx8jkfY2RZEdwv/2m9dXYZftBPqKIJvWwPAx4NGA1vy2FpV2ofPk+m8qayZ09fBzJqutPMNCCjGQQkA0HJDTus5vrtoJNwRcE0zUYrNYImdEVqHQzX5RCfbZ+sBg+Y0IZjI7wEjQw2EEc6zu7tKh4IkosbN8zz5+2bEVnX/yLcCpOwJ/ehE1pNGeYdljrVdsQGmHhEXNQQAhtwnoz0bsVIKrwlXKNIzt9SX3oqFWoK46ReV236NmCR/wrCWcWWLDGdkgj4rdSFaY5ah8vXYeJMe9zfhsLD7YpFN8blvwGk7P5HjZg7hM+hrW82bLkCnkp7Xot4nvELtKBKj3GDpVdUOPwzVm1pxGMjuuYQZSyIm59ldcVn23/6yGvnUInHlXfZ2Y78V4S/x5nXS/b8qJqSx5DrPRRT/IrUjT6Mtvg+HdOVgLmq9yo0B4L9lVUwM866wMQP1Fs5hC1dbJQbQByqnpHra4gBmT3zDq8AgcsOBYesgn09nrkNnXzGbEziVXbxJjiNFjdSKsU2m0GKlzcLqufnI7+n8w3WmzFdeJVA2CqzAO3fvPstuVJGJC5uDXvCG/O1q/Fsb0CK+JqMeg1lLCY0P6XeMvyEpjzMreP8LDADeQvB/OCr31k2QE3HrBTnwoYhDdFfZk8oGnuXtDsF+Q0YMSrJW7djvfVPmbre4ZSJQXX75fJkE/7d7lhLdYYUrYNJ7IrBdZvPNRbDFRGQSgrtxHfVhzPQ9X8ZGobV3P6vB5lcEo7MGhiZGoxyw3lCTG9DEhbflLOWHCcQuDjPcivW5DEsVRWHh6LvPF8SIquc7U351JpKjlwPe0WzRNomswaebOKPfGECz6nIYMvRqAoGSd9NMkH9oft2u+njJjc0wojOS6aZjivL65g8Owes+mNenzWRgYoLAuj4Y2KxqyCoS6ShFsTi8HW49m56PoNrwJ1rurAzL4ivnLoDVUb+6QOxVNRP+ogtYGX5z5lJzFSSFSN0ar0jUNBs1/r6Xd4H4NZAiUKwg+B1kBQkcSCMdySl0pGiUfdkbWBh+WQyAszkF8jk/Ex3qxXa1ATajZihMbar7uX1XZBIhdqe+XyWwPS9/17T0ONCW7BREFL6V5AwWOjnGbvIEsDKdqnXB2Xj4XjwU8DkUIAFLT4tTJx9dbbJjT4+jPAxtCMBQNeqX5h6jEy+F8qZfHlwvB6zYMpLw9UEjMbahXaMnCGOHm2mSdND6cwbkQLuRTZssH0pSlZ0eB1JbcPqO4/uHKdYey4yFMIE5hRJxJD+aUp8y2xaWxZ/IbW9mTV/PYJzTROSquRs2n74lYkMV/L8nsUzMtziBhEnX8rgKXm+dZOFpr0kVq31BWSkpwadgH/3XGffnqK3TeU4OKIt8kTq89dAhWBxhd1I63j0QAt+gXRvwVRRCA2lAg4hon5/7jslBY+8JuA5GyJNRDZlP3FDnXDVq+OL3Toek00Hc+E151etDYt0toUoUp0H1iNxgCWOpElKy1etlHtf7bBHlcioEVieETFM4hDOQVPFYASZ188Hjk/PCB7pDRCWhPYQDYm0XImSO8Un6qm2X1y2RWzEnyQVLjcHhQg5EgUFMZIas3YJvqg+NLtADVmPIwC4GjvRynCi8IBeOxpahJPissiOl0LFAPD63j6ZmQhIG7/p7yKCnEFZVE3ter4ww4OWARRtBe1GRWFSOcKzxfJ7umj3jSuSzkkllkZDDALiAeTaPSWS5gE+WWkuMc8P+vucypHyLc6CLdhyTwGS7GpqY0vmmRTgdQYe9n0Cg5Lby1Pb6wjamYuuPagbtA1BrDAuLl9DNeoz6iKlXdJQ72ekteIZotLLM9RIOEVheIVZ15RZnwTenlX+D5giRhFgyyqmP+v8DrHQUjqvogmByBJvxiXrk8a9Ru5hR+SK+4jWBnZ96eZV0FDBmhOV6FAkB0tXr32NPLPgJa2Gq+9nV9G3gGKYZMC7sN1Qakc+hZGXOHDstPBXR0LTYCYPYmt+4WMHaYGj+J8cZJxc8BQyJ1uE62QfMFhHB+QI1ndntIeRtH57VBOn1o0d7PTzLVI6tve6KNjvOyNWcrGIRLOME2DaBdHwW4Bd0ROK6g6sjxCdpvK2chnY6nyayiaC8izzxQWS8ckPFOeyQ82M/pJVDTonjrvpJctQdJStESyFRpbnCmUQM3LSiyuS4+ZlsQSgYX6HruoK5Gu34D4xnsqr01wKNyAIBe05+/ZddVHm0Xj+5PT3z1W0AAD1RCWIag6bRGjPvw9mmgEIXB9mirxBtZJX3dIM6qTYCIeH04JL37vnFbLH6p7t9KxAsHBZAgorbOFX/+xA9P48osSQU5f30jnpqRBJ1ZwSqKWiDx5rr4j6e6HdU03AEMqZKodqjCyU4lMwFCAr/9OqtYhLhON/gdechke0sTBMIO76VCVHxU32QvALLc8fyIoLQEHKLfmQ1yXt72kbRqVvcmjR9U5540yhjkcDFdhZmXzi6mgHX7CDtFKrAJBYuskexLp2TsqFD9W5pqRkQw60oPaBPQ3fcU/WKxpmrCQKVfGVLpOIGiQCpgiOcbHzmn3pgWetZgjMpxvCcTipN70AZVjUzuLb2NkyloF+r1jVTdFrqe5x8nJiRvm/PD8LCZZ6EVxw4H92N2YeRP7SGdob0awZlcU6Xpb4IIaN5LvrxFsi8AKgmdgUOlFa6sdmkTBQO994x/wSYJDxIAY4jTTPQJwmDDOtslN+fnZdw2BNSnI8BjkHQFl3Qvx5tZ4lfrLSF2nPSQpRMEDQZm1CecMjf9v0fEWQWyE/ZVny64wZosLMiwjArgw98IEQjLK+OhNEK1LQppiUqtyAZYbMXITs8Knyw/sakrCIETCYMHyxapMc657WhTIl2gB3a9w3dCpw5y8rA9eDEpkeLm05OVeGzQ5IdlK6qotv6mVvIVUGaKSGXIwrx67tiIrMboZjYgQ4qsPPyAKXcFtTkam8pRoxgmeXR8qGsGldfwRI3EaMpwzmdsorqHrEMG+AeMcw6Hz4WC9qE6vi1XkFKaBYqWauf4JxrNl6tIC5oWo8xbdvYYM4/2SCiYhbsQdVpXdawPhBGOC4FAIaWS5xmhjO+TlN2+oGq1E8IQt3XyjjCh8iDIzzAGzvVz0Box/+CKIhUcd5VpVIk/m6DSYDqeZCF383fnVjl3AEBoC7WM/9hS5yAmxyov4CdqsgdTDkD7RaW3UFCDpnfpdvtKAsklUUhHOU8sFVpAPtEmOXIgF+TeLt0ZI8A2IMICr4hTNolJ9+j/KTw/eYfU0WHn5p12tHrAlC0QdXYBSkoutqnGc59l048OZL7cxIylRBE26Hyk0XohQM9nGTZVxZhDCXla18OJP1RhHtc/1WKGK6b4XiXSW4MN0VwwI4OSIk7JVmnjztDSrGyXqbaCeEXud8iZlakzhqOPxyK+vChY0hq2O097Vq+0Z1NK5MvyHzdbYFcK7171f+cvTp8q5lMGCtRAE2aFvd3WdM/wrUEqSk7OxdNcL1G2p6qBN+nWLTU8T5bdy04cU3WgDgkIYZnOQ2sag2uFewY49N/mR+ETkG2yEFAdIHcxfCq4xd263Z/AsnyAW8zgxbBczHVRBKHLEHQaVhvldKgy7WcEGuarLeP3wbctJMM905Sq6iv1MEX1P+bmdD+4sa4LQThm883DJd1zCjnRycWkZtCc3SPKdtR1iugIZsj5fA+LUZzc6QK1KMCgppdb8HqIyY8fwpD+UF9AtWLQcnGXZDlvDGfONapkohw2J4/jwz4RNaD5iI+/BZ47qnMvK0FIqsIlluEQDu1cTsU0kmsTa9nzoOSFVzQm+P8ncqI5hA+hAxw6qeafIzcB4h2d77EGyDaeIzYRnm4g3NS1qAiPP'


def require(allowed, reason):
    if not allowed:
        raise RuntimeError('HOLD_I39_INGRESS_' + reason)


def trusted_file(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    handle = os.fdopen(fd, 'rb')
    try:
        meta = os.fstat(handle.fileno())
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and meta.st_nlink == 1
                and meta.st_mode & 0o077 == 0 and 0 < meta.st_size <= limit, 'FILE_SCOPE')
    except BaseException:
        handle.close()
        raise
    return handle


def verify_ingress():
    for directory in (KEY_DIR, *KEY_DIR.parents):
        meta = directory.lstat()
        require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0
                and meta.st_mode & 0o022 == 0, 'DIRECTORY_SCOPE')


def open_entry():
    verify_ingress()
    cert = KEY_DIR / 'ingress.pem'
    key = KEY_DIR / 'ingress.key'
    with trusted_file(cert, 3000) as handle:
        require(sha256(handle.read(3001)).hexdigest() == CERT_SHA, 'CERT_PIN')
    with trusted_file(key, 6000):
        pass
    ciphertext = base64.b64decode(CIPHER_B64, validate=True)
    require(0 < len(ciphertext) <= 80000 and sha256(ciphertext).hexdigest() == CIPHER_SHA, 'CIPHER_PIN')
    decrypted = subprocess.run(('/usr/bin/openssl', 'cms', '-decrypt', '-binary', '-inform', 'DER',
                                '-recip', str(cert), '-inkey', str(key)),
                               input=ciphertext, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, timeout=8, check=False)
    packet = decrypted.stdout
    require(decrypted.returncode == 0 and 0 < len(packet) <= 80000
            and sha256(packet).hexdigest() == PACKET_SHA, 'PACKET_PIN')
    with gzip.GzipFile(fileobj=io.BytesIO(packet), mode='rb') as handle:
        module = handle.read(80001)
    require(0 < len(module) <= 80000 and sha256(module).hexdigest() == ENTRY_SHA, 'ENTRY_PIN')
    return module


def main():
    labels = {os.environ[key].removeprefix('C.') for key in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
              if os.environ.get(key)}
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(os.geteuid() == os.getegid() == 0 and labels == {'60509551'}
            and re.fullmatch(r'[1-9][0-9]{0,19}', request) is not None
            and re.fullmatch(r'[a-f0-9]{40}', source) is not None, 'OWNER_SCOPE')
    module = open_entry()
    exec(compile(module, '<pinned-operator-reviewed-I39>', 'exec'), {'__name__': '__main__'})


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as failure:
        tag = str(failure)
        print('NOX_MAINT_RESULT=' + (tag if re.fullmatch(r'HOLD_I39_INGRESS_[A-Z_]+', tag)
                                   else 'HOLD_I39_INGRESS_UNAVAILABLE'), flush=True)
        raise SystemExit(2) from None
