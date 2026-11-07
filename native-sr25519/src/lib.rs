//! Minimal C ABI for Schnorrkel. No API exports secret material.
use schnorrkel::{signing_context, ExpansionMode, MiniSecretKey};
use zeroize::Zeroize;

unsafe fn pair(seed: *const u8) -> schnorrkel::Keypair {
    let mut bytes = [0u8; 32];
    bytes.copy_from_slice(std::slice::from_raw_parts(seed, 32));
    let key = MiniSecretKey::from_bytes(&bytes).unwrap();
    bytes.zeroize();
    key.expand_to_keypair(ExpansionMode::Ed25519)
}

#[no_mangle]
pub unsafe extern "C" fn satooshi_public(seed: *const u8, out: *mut u8) -> i32 {
    if seed.is_null() || out.is_null() { return -1; }
    let mut key = pair(seed);
    std::ptr::copy_nonoverlapping(key.public.to_bytes().as_ptr(), out, 32);
    key.secret.zeroize();
    0
}

#[no_mangle]
pub unsafe extern "C" fn satooshi_sign(seed: *const u8, msg: *const u8, len: usize, out: *mut u8) -> i32 {
    if seed.is_null() || msg.is_null() || out.is_null() || len == 0 || len > 32768 { return -1; }
    let mut key = pair(seed);
    let signature = key.sign(signing_context(b"substrate").bytes(std::slice::from_raw_parts(msg, len)));
    std::ptr::copy_nonoverlapping(signature.to_bytes().as_ptr(), out, 64);
    key.secret.zeroize();
    0
}
