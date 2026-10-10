import json
import uuid

import pytest

from app.services.license_service import (
    LicenseError,
    LicenseService,
    generate_license_keypair,
    issue_license,
)


@pytest.fixture
def signing_keys(tmp_path):
    private_key = tmp_path / "publisher-private.pem"
    public_key = tmp_path / "license_public_key.pem"
    generate_license_keypair(private_key, public_key, "safe-test-passphrase")
    return private_key, public_key


def test_license_request_reuses_installation_id_and_contains_store_name(
    tmp_path,
):
    service = LicenseService(tmp_path / "data", device_id="a" * 64)
    first_request = tmp_path / "first.posreq"
    second_request = tmp_path / "second.posreq"

    service.create_request("Toko Contoh", first_request)
    service.create_request("Toko Contoh", second_request)

    first = json.loads(first_request.read_text(encoding="utf-8"))
    second = json.loads(second_request.read_text(encoding="utf-8"))
    assert first["installation_id"] == second["installation_id"]
    assert str(uuid.UUID(first["installation_id"])) == first["installation_id"]
    assert first["store_name"] == "Toko Contoh"


def test_issued_license_verifies_for_requesting_installation(
    tmp_path,
    signing_keys,
):
    private_key, public_key = signing_keys
    service = LicenseService(tmp_path / "data", device_id="a" * 64)
    request_path = tmp_path / "request.posreq"
    license_path = tmp_path / "license.poslic"
    service.create_request("Toko Contoh", request_path)
    request = json.loads(request_path.read_text(encoding="utf-8"))

    issue_license(
        request_path,
        license_path,
        store_name="Toko Contoh",
        private_key_path=private_key,
        passphrase="safe-test-passphrase",
    )

    payload = LicenseService.verify_license_file(
        license_path,
        expected_installation_id=request["installation_id"],
        expected_device_id="a" * 64,
        public_key_path=public_key,
    )
    assert payload["store_name"] == "Toko Contoh"
    assert payload["installation_id"] == request["installation_id"]
    assert payload["expires_at"] is None


def test_activation_persists_a_valid_license_for_later_offline_startup(
    tmp_path,
    signing_keys,
):
    private_key, public_key = signing_keys
    service = LicenseService(
        tmp_path / "data",
        device_id="a" * 64,
        public_key_path=public_key,
    )
    request_path = tmp_path / "request.posreq"
    license_path = tmp_path / "license.poslic"
    service.create_request("Toko Contoh", request_path)
    issue_license(
        request_path,
        license_path,
        store_name="Toko Contoh",
        private_key_path=private_key,
        passphrase="safe-test-passphrase",
    )

    assert service.license_status() == (False, "Lisensi belum dipasang.")
    assert service.activate(license_path) == "Toko Contoh"
    assert service.license_path.is_file()
    assert service.license_status() == (
        True,
        "Lisensi aktif untuk Toko Contoh.",
    )


def test_license_cannot_be_used_for_another_installation(
    tmp_path,
    signing_keys,
):
    private_key, public_key = signing_keys
    service = LicenseService(tmp_path / "data", device_id="a" * 64)
    request_path = tmp_path / "request.posreq"
    license_path = tmp_path / "license.poslic"
    service.create_request("Toko Contoh", request_path)
    issue_license(
        request_path,
        license_path,
        store_name="Toko Contoh",
        private_key_path=private_key,
        passphrase="safe-test-passphrase",
    )

    with pytest.raises(LicenseError, match="instalasi POS lain"):
        LicenseService.verify_license_file(
            license_path,
            expected_installation_id=str(uuid.uuid4()),
            expected_device_id="a" * 64,
            public_key_path=public_key,
        )


def test_modified_license_payload_fails_signature_validation(
    tmp_path,
    signing_keys,
):
    private_key, public_key = signing_keys
    service = LicenseService(tmp_path / "data", device_id="a" * 64)
    request_path = tmp_path / "request.posreq"
    license_path = tmp_path / "license.poslic"
    service.create_request("Toko Contoh", request_path)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    issue_license(
        request_path,
        license_path,
        store_name="Toko Contoh",
        private_key_path=private_key,
        passphrase="safe-test-passphrase",
    )
    license_document = json.loads(license_path.read_text(encoding="utf-8"))
    license_document["payload"]["store_name"] = "Toko Diubah"
    license_path.write_text(json.dumps(license_document), encoding="utf-8")

    with pytest.raises(LicenseError, match="Tanda tangan lisensi"):
        LicenseService.verify_license_file(
            license_path,
            expected_installation_id=request["installation_id"],
            expected_device_id="a" * 64,
            public_key_path=public_key,
        )


def test_private_key_cannot_be_overwritten(tmp_path, signing_keys):
    private_key, public_key = signing_keys

    assert private_key.read_bytes().startswith(
        b"-----BEGIN ENCRYPTED PRIVATE KEY-----"
    )
    with pytest.raises(LicenseError, match="tidak ditimpa"):
        generate_license_keypair(private_key, public_key, "another-test-pass")


def test_short_private_key_passphrase_does_not_create_key_files(tmp_path):
    private_key = tmp_path / "publisher-private.pem"
    public_key = tmp_path / "license_public_key.pem"

    with pytest.raises(LicenseError, match="minimal 12 karakter"):
        generate_license_keypair(private_key, public_key, "too-short")

    assert not private_key.exists()
    assert not public_key.exists()
