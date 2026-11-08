SATOOSHI_RUNTIME_VERSION = 0.3.0
SATOOSHI_RUNTIME_SITE = $(SATOOSHI_FIRMWARE_DIR)/device
SATOOSHI_RUNTIME_SITE_METHOD = local
define SATOOSHI_RUNTIME_BUILD_CMDS
	$(TARGET_CC) -Os -march=armv6zk -marm -mfloat-abi=soft \
		-nostdlib -nostartfiles -static -fno-stack-protector \
		-o $(@D)/early-splash $(SATOOSHI_FIRMWARE_DIR)/image/early-splash.c
endef
define SATOOSHI_RUNTIME_INSTALL_TARGET_CMDS
	mkdir -p $(TARGET_DIR)/opt/satooshi/device $(TARGET_DIR)/opt/satooshi/image
	rsync -a --exclude __pycache__ --exclude '*.pyc' $(@D)/satooshi $(TARGET_DIR)/opt/satooshi/device/
	$(INSTALL) -m 0755 $(@D)/early-splash $(TARGET_DIR)/opt/satooshi/image/early-splash
endef
$(eval $(generic-package))
