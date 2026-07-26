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

if [ -z "$src" ] || [ ! -f "$src" ] || [ ! -s "$src" ]; then
  echo "Image builder did not produce a non-empty image at: $src" >&2
  exit 1
fi

case "$output" in
  *.img) ;;
  *) echo "Output image must end in .img so the artifact unzips to a flashable OS image: $output" >&2; exit 1 ;;
esac

install -d "$artifact_dir"
rm -f "$output" "$output.xz" "$artifact_dir/$output" "$artifact_dir/$output.xz" \
  "$artifact_dir/$output.sha256" "$artifact_dir/$output.xz.sha256" \
  "$artifact_dir/$output.fdisk.txt"

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

if ! fdisk -l "$output" | tee "$artifact_dir/$output.fdisk.txt"; then
  echo "fdisk could not read the generated image partition table" >&2
  exit 1
fi
if ! grep -Eq 'Disklabel type: dos' "$artifact_dir/$output.fdisk.txt"; then
  echo "Image does not use the expected Raspberry Pi MBR partition table" >&2
  exit 1
fi
if ! grep -Eq 'W95 FAT32' "$artifact_dir/$output.fdisk.txt" || ! grep -Eq 'Linux' "$artifact_dir/$output.fdisk.txt"; then
  echo "Image does not contain the expected Raspberry Pi boot FAT32 and Linux root partitions" >&2
  exit 1
fi

# Upload the raw .img inside the GitHub artifact ZIP so unzipping the artifact
# immediately yields a flashable OS image file. Also provide .xz for tools that
# prefer compressed images, and verify that decompression recreates the exact
# non-empty byte count.
cp "$output" "$artifact_dir/$output"
( cd "$artifact_dir" && sha256sum "$output" > "$output.sha256" && sha256sum -c "$output.sha256" )

xz -0 -T 0 --check=crc64 --keep -v "$output"
xz -t "$output.xz"
uncompressed_bytes=$(xz --robot --list "$output.xz" | awk -F'\t' '$1 == "totals" { print $5 }')
if [ "$uncompressed_bytes" != "$image_bytes" ]; then
  echo "Compressed image expands to ${uncompressed_bytes} bytes, expected ${image_bytes}" >&2
  exit 1
fi

xz -dc "$output.xz" | cmp - "$output"
mv "$output.xz" "$artifact_dir/"
( cd "$artifact_dir" && sha256sum "$output.xz" > "$output.xz.sha256" && sha256sum -c "$output.xz.sha256" )

artifact_image_bytes=$(stat -c '%s' "$artifact_dir/$output")
if [ "$artifact_image_bytes" != "$image_bytes" ]; then
  echo "Artifact image size changed to ${artifact_image_bytes} bytes, expected ${image_bytes}" >&2
  exit 1
fi

cat > "$artifact_dir/README.txt" <<EOF
RPINAS image artifact

Flash $output to a Raspberry Pi SD card or USB boot device after downloading and unzipping this artifact.
$output.xz is the verified compressed copy of the same raw image.
Use sha256sum -c *.sha256 to verify downloaded files before flashing.
EOF
