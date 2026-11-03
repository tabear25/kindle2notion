#!/usr/bin/env bash
# Build the Android app in android/ into a signed APK.
#
# No Gradle / Android SDK manager on purpose: the cloud sessions this repo is
# maintained in cannot reach Google's download hosts (dl.google.com,
# maven.google.com). Everything below comes from places that are reachable:
#
#   - Ubuntu packages: dx, zipalign, apksigner and the API-23 android.jar
#       sudo apt-get install -y dalvik-exchange zipalign apksigner android-sdk-platform-23
#   - aapt2 and the Android framework resources (needed for shortcut and
#     widget attributes newer than API 23), taken from the apktool-cli jar on
#     Maven Central — downloaded once and checked against a pinned SHA-256
#   - a JDK 17+ (javac, java, keytool)
#
# Usage:
#   android/build.sh          unit tests, then build + sign -> android/build/kindle2notion.apk
#   android/build.sh test     unit tests only (plain JVM, no Android tools needed)
#
# Signing: set K2N_KEYSTORE + K2N_KEYSTORE_PASS (and K2N_KEY_ALIAS, default
# "k2n") to sign with your own key. Without them a throwaway key is created in
# android/build/. Android installs an update over an existing app only when it
# is signed with the same key, so keep the keystore you sign with.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$HERE/build"
WORK="$BUILD/work"
CACHE="${K2N_TOOLS_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/k2n-android}"
PACKAGE_DIR="io/github/tabear25/kindle2notion"

APKTOOL_VERSION="2.12.1"
APKTOOL_SHA256="4e04969072555340cab1fd44d0d8e619937d9bd0552931e29cfa870c3b71f2d3"
APKTOOL_URL="https://repo.maven.apache.org/maven2/org/apktool/apktool-cli/${APKTOOL_VERSION}/apktool-cli-${APKTOOL_VERSION}.jar"

ANDROID_JAR="${K2N_ANDROID_JAR:-/usr/lib/android-sdk/platforms/android-23/android.jar}"
DX="${K2N_DX:-dalvik-exchange}"

die() {
  echo "error: $*" >&2
  exit 1
}

run_tests() {
  local out="$BUILD/test-classes"
  rm -rf "$out"
  mkdir -p "$out"
  javac -encoding UTF-8 -d "$out" \
    "$HERE/src/$PACKAGE_DIR/LaunchUrls.java" \
    "$HERE/test/$PACKAGE_DIR/LaunchUrlsTest.java"
  java -cp "$out" io.github.tabear25.kindle2notion.LaunchUrlsTest
}

ensure_tools() {
  local tool
  for tool in javac keytool zip unzip curl sha256sum zipalign apksigner "$DX"; do
    command -v "$tool" >/dev/null 2>&1 || die "'$tool' not found — see the toolchain notes at the top of $0"
  done
  [ -f "$ANDROID_JAR" ] || die "$ANDROID_JAR not found (apt-get install android-sdk-platform-23)"

  local jar="$CACHE/apktool-cli-${APKTOOL_VERSION}.jar"
  mkdir -p "$CACHE"
  if [ ! -f "$jar" ]; then
    curl -fsSL -o "$jar.part" "$APKTOOL_URL"
    mv "$jar.part" "$jar"
  fi
  if ! echo "$APKTOOL_SHA256  $jar" | sha256sum -c --quiet -; then
    rm -f "$jar"
    die "checksum mismatch for $jar (deleted; rerun to download again)"
  fi

  AAPT2="$CACHE/aapt2-${APKTOOL_VERSION}"
  FRAMEWORK="$CACHE/android-framework-${APKTOOL_VERSION}.jar"
  if [ ! -x "$AAPT2" ] || [ ! -f "$FRAMEWORK" ]; then
    local tmp="$CACHE/extract"
    rm -rf "$tmp"
    unzip -q -o -j "$jar" prebuilt/linux/aapt2_64 prebuilt/android-framework.jar -d "$tmp"
    mv "$tmp/aapt2_64" "$AAPT2"
    mv "$tmp/android-framework.jar" "$FRAMEWORK"
    chmod +x "$AAPT2"
    rm -rf "$tmp"
  fi
}

ensure_keystore() {
  KEY_ALIAS="${K2N_KEY_ALIAS:-k2n}"
  if [ -n "${K2N_KEYSTORE:-}" ]; then
    [ -f "$K2N_KEYSTORE" ] || die "K2N_KEYSTORE=$K2N_KEYSTORE does not exist"
    [ -n "${K2N_KEYSTORE_PASS:-}" ] || die "set K2N_KEYSTORE_PASS for $K2N_KEYSTORE"
    KEYSTORE="$K2N_KEYSTORE"
    SIGN_PASS="$K2N_KEYSTORE_PASS"
    return
  fi
  KEYSTORE="$BUILD/throwaway.jks"
  local pass_file="$BUILD/throwaway.pass"
  if [ ! -f "$KEYSTORE" ]; then
    echo "warning: K2N_KEYSTORE not set — creating a throwaway signing key in $BUILD" >&2
    (umask 077 && head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' > "$pass_file")
    K2N_NEW_PASS="$(cat "$pass_file")" keytool -genkeypair -noprompt \
      -keystore "$KEYSTORE" -storetype PKCS12 -alias "$KEY_ALIAS" \
      -keyalg RSA -keysize 3072 -validity 10950 -dname "CN=kindle2notion" \
      -storepass:env K2N_NEW_PASS -keypass:env K2N_NEW_PASS
  fi
  SIGN_PASS="$(cat "$pass_file")"
}

build_apk() {
  rm -rf "$WORK"
  mkdir -p "$WORK/gen" "$WORK/classes"

  # 1. Resources + manifest -> base.apk, plus R.java for the code
  "$AAPT2" compile --dir "$HERE/res" -o "$WORK/res.zip"
  "$AAPT2" link -o "$WORK/base.apk" -I "$FRAMEWORK" \
    --manifest "$HERE/AndroidManifest.xml" --java "$WORK/gen" "$WORK/res.zip"

  # 2. Java -> classes.dex (API-23 classes are enough: nothing newer is called)
  find "$HERE/src" "$WORK/gen" -name '*.java' > "$WORK/sources.txt"
  javac -encoding UTF-8 -source 8 -target 8 -Xlint:-options \
    -bootclasspath "$ANDROID_JAR" -d "$WORK/classes" "@$WORK/sources.txt"
  "$DX" --dex --min-sdk-version=26 --output="$WORK/classes.dex" "$WORK/classes"

  # 3. Package, align (resources.arsc must be 4-byte aligned), then sign v2/v3
  cp "$WORK/base.apk" "$WORK/unaligned.apk"
  (cd "$WORK" && zip -q -X unaligned.apk classes.dex)
  zipalign -f -p 4 "$WORK/unaligned.apk" "$WORK/aligned.apk"
  K2N_SIGN_PASS="$SIGN_PASS" apksigner sign \
    --ks "$KEYSTORE" --ks-key-alias "$KEY_ALIAS" \
    --ks-pass env:K2N_SIGN_PASS --key-pass env:K2N_SIGN_PASS \
    --out "$BUILD/kindle2notion.apk" "$WORK/aligned.apk"
  apksigner verify --verbose "$BUILD/kindle2notion.apk" | grep -E "^Verified using|^Verifies"
}

case "${1:-build}" in
  test)
    run_tests
    ;;
  build)
    mkdir -p "$BUILD"
    run_tests
    ensure_tools
    ensure_keystore
    build_apk
    echo "built: $BUILD/kindle2notion.apk"
    ;;
  *)
    die "usage: $0 [build|test]"
    ;;
esac
