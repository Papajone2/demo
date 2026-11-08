SATOOSHI_NATIVE_VERSION = 0.1.0
SATOOSHI_NATIVE_SITE = $(SATOOSHI_FIRMWARE_DIR)/native-sr25519
SATOOSHI_NATIVE_SITE_METHOD = local
SATOOSHI_NATIVE_DEPENDENCIES = host-rustc
define SATOOSHI_NATIVE_BUILD_CMDS
	cd $(@D) && $(TARGET_MAKE_ENV) $(PKG_CARGO_ENV) \
		CARGO_TARGET_ARM_UNKNOWN_LINUX_GNUEABIHF_RUSTFLAGS="-C target-cpu=arm1176jzf-s -Clink-arg=-Wl,--allow-multiple-definition" \
		cargo build --release --locked --offline \
		--config 'source.crates-io.replace-with="satooshi-vendored"' \
		--config 'source.satooshi-vendored.directory="$(SATOOSHI_CARGO_VENDOR)"'
endef
define SATOOSHI_NATIVE_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/target/$(RUSTC_TARGET_NAME)/release/libsatooshi_sr25519.so \
		$(TARGET_DIR)/opt/satooshi/lib/libsatooshi_sr25519.so
endef
$(eval $(generic-package))
