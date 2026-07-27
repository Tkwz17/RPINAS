#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "Usage: $0 SOURCE_IMAGE OUTPUT_IMAGE MIN_BYTES ARTIFACT_DIR" >&2
  exit 64
fi

src="$1"
output="$2"
min_bytes="$3"
artifact_dir="$4"
fdisk_report="$(mktemp /tmp/rpinas-fdisk-XXXXXX.txt)"
tmp_zip="$(mktemp /tmp/rpinas-zipcheck-XXXXXX.zip)"
tmp_unzip_dir="$(mktemp -d /tmp/rpinas-zipcheck-XXXXXX)"

cleanup() {
  rm -f "$fdisk_report" "$tmp_zip"
  rm -rf "$tmp_unzip_dir"
}

trap cleanup EXIT

if [ -z "$src" ] || [ ! -f "$src" ] || [ ! -s "$src" ]; then
  echo "Image builder did not produce a non-empty image at: $src" >&2
  exit 1
fi

case "$output" in
  *.img) ;;
  *) echo "Output image must end in .img so the artifact unzips to a flashable OS image: $output" >&2; exit 1 ;;
esac

rm -rf "$artifact_dir"
install -d "$artifact_dir"
rm -f "$output"

# Re-materialize the raw image without sparse holes before artifact upload.
# Sparse files can appear as zero-byte or truncated images after artifact ZIP
# download/extraction in some clients, so copy the full byte stream and fsync it.
dd if="$src" of="$output" bs=16M status=progress conv=fsync
sync -f "$output" 2>/dev/null || sync

image_bytes=$(stat -c '%s' "$output")
if [ "$image_bytes" -lt "$min_bytes" ]; then
  echo "Image is unexpectedly small: ${image_bytes} bytes (minimum ${min_bytes})" >&2
  exit 1
fi
src_bytes=$(stat -c '%s' "$src")
if [ "$src_bytes" != "$image_bytes" ]; then
  echo "Copied image size ${image_bytes} does not match source image size ${src_bytes}" >&2
  exit 1
fi
cmp "$src" "$output"
src_sha256="$(sha256sum "$src" | awk '{print $1}')"
image_sha256="$(sha256sum "$output" | awk '{print $1}')"
if [ "$src_sha256" != "$image_sha256" ]; then
  echo "Copied image checksum ${image_sha256} does not match source checksum ${src_sha256}" >&2
  exit 1
fi

if ! fdisk -l "$output" | tee "$fdisk_report"; then
  echo "fdisk could not read the generated image partition table" >&2
  exit 1
fi
if ! grep -Eq 'Disklabel type: dos' "$fdisk_report"; then
  echo "Image does not use the expected Raspberry Pi MBR partition table" >&2
  exit 1
fi
if ! grep -Eq 'W95 FAT32' "$fdisk_report" || ! grep -Eq 'Linux' "$fdisk_report"; then
  echo "Image does not contain the expected Raspberry Pi boot FAT32 and Linux root partitions" >&2
  exit 1
fi

# Upload only the raw .img inside the GitHub artifact ZIP so unzipping the
# artifact immediately yields one flashable OS image file.
cp "$output" "$artifact_dir/$output"
cmp "$artifact_dir/$output" "$output"

artifact_image_bytes=$(stat -c '%s' "$artifact_dir/$output")
if [ "$artifact_image_bytes" != "$image_bytes" ]; then
  echo "Artifact image size changed to ${artifact_image_bytes} bytes, expected ${image_bytes}" >&2
  exit 1
fi
artifact_sha256="$(sha256sum "$artifact_dir/$output" | awk '{print $1}')"
if [ "$artifact_sha256" != "$image_sha256" ]; then
  echo "Artifact image checksum ${artifact_sha256} does not match expected ${image_sha256}" >&2
  exit 1
fi

mapfile -t artifact_entries < <(find "$artifact_dir" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
if [ "${#artifact_entries[@]}" -ne 1 ] || [ "${artifact_entries[0]}" != "$output" ]; then
  echo "Artifact directory must contain exactly one .img file named $output" >&2
  exit 1
fi

case "${artifact_entries[0]}" in
  *.img) ;;
  *)
    echo "Artifact directory entry is not a .img file: ${artifact_entries[0]}" >&2
    exit 1
    ;;
esac

if [ ! -s "$artifact_dir/$output" ]; then
  echo "Required artifact image is missing or empty: $artifact_dir/$output" >&2
  exit 1
fi

# Validate common unzip extraction flow by creating a representative ZIP and
# confirming it expands to one flashable .img file with unchanged bytes.
zip -j -q "$tmp_zip" "$artifact_dir/$output"
mapfile -t zip_entries < <(unzip -Z1 "$tmp_zip")
if [ "${#zip_entries[@]}" -ne 1 ] || [ "${zip_entries[0]}" != "$output" ]; then
  echo "ZIP extraction check failed: expected exactly one entry named $output" >&2
  exit 1
fi

unzip -q "$tmp_zip" -d "$tmp_unzip_dir"
if [ ! -s "$tmp_unzip_dir/$output" ]; then
  echo "ZIP extraction check failed: extracted image missing or empty: $output" >&2
  exit 1
fi

unzipped_bytes=$(stat -c '%s' "$tmp_unzip_dir/$output")
if [ "$unzipped_bytes" != "$image_bytes" ]; then
  echo "ZIP extraction check failed: extracted size ${unzipped_bytes} does not match expected ${image_bytes}" >&2
  exit 1
fi

unzipped_sha256="$(sha256sum "$tmp_unzip_dir/$output" | awk '{print $1}')"
if [ "$unzipped_sha256" != "$image_sha256" ]; then
  echo "ZIP extraction check failed: extracted checksum ${unzipped_sha256} does not match expected ${image_sha256}" >&2
  exit 1
fi
