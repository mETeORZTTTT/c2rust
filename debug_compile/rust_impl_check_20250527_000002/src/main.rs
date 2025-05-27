// 自动生成的编译验证代码
#![allow(unused_variables, dead_code, unused_imports, non_camel_case_types, non_snake_case, non_upper_case_globals)]

use std::os::raw::*;
use std::ptr;
use std::ffi::c_void;
extern crate libc;

fn main() {}

// ================ 类型定义和已实现函数 ================

// 项目: zopfli::defines::HASH_MASK
const HASH_MASK: u32 = 32767;

// 项目: zopfli::defines::HASH_SHIFT
const HASH_SHIFT: usize = 5;

// 项目: zopfli::defines::NUM
pub const NUM: i32 = 9; // Good value: 9.

// 项目: zopfli::defines::ZOPFLI_NUM_LL
const ZOPFLI_NUM_LL: usize = 288;

// 项目: zopfli::defines::ZOPFLI_NUM_D
pub const ZOPFLI_NUM_D: usize = 32;

// 项目: zopfli::defines::ZOPFLI_CACHE_LENGTH
const ZOPFLI_CACHE_LENGTH: usize = 8;

// 项目: zopfli::defines::ZOPFLI_MIN_MATCH
pub const ZOPFLI_MIN_MATCH: usize = 3;

// 项目: zopfli::defines::ZOPFLI_MAX_MATCH
const ZOPFLI_MAX_MATCH: usize = 258;

// 项目: zopfli::defines::ZOPFLI_MAX_CHAIN_HITS
pub const ZOPFLI_MAX_CHAIN_HITS: usize = 8192;

// 项目: zopfli::defines::ZOPFLI_WINDOW_SIZE
const ZOPFLI_WINDOW_SIZE: usize = 32768;

// 项目: zopfli::defines::ZOPFLI_WINDOW_MASK
const ZOPFLI_WINDOW_MASK: usize = ZOPFLI_WINDOW_SIZE - 1;

// 项目: zopfli::defines::ZOPFLI_LARGE_FLOAT
const ZOPFLI_LARGE_FLOAT: f64 = 1e30;

// 项目: zopfli::defines::ZOPFLI_MASTER_BLOCK_SIZE
pub const ZOPFLI_MASTER_BLOCK_SIZE: usize = 1_000_000;

// 项目: zopfli::typedefs::typedef double FindMinimumFun (size_t i ,void *context )
type FindMinimumFun = unsafe extern "C" fn(i: usize, context: *mut core::ffi::c_void) -> f64;

// 项目: zopfli::typedefs::typedef double CostModelFun (unsigned litlen ,unsigned dist ,void *context )
type CostModelFun = unsafe extern "C" fn(litlen: u32, dist: u32, context: *mut core::ffi::c_void) -> f64;

// 项目: zopfli::structs::ZopfliLZ77Store
#[derive(Debug, Clone)]
struct ZopfliLZ77Store {
    litlens: *mut u16, // Lit or len.
    dists: *mut u16, // If 0: indicates literal in corresponding litlens,
                     // if > 0: length in corresponding litlens, this is the distance.
    size: usize,
    data: *const u8, // Original data
    pos: *mut usize, // Position in data where this LZ77 command begins
    ll_symbol: *mut u16, // Cumulative histograms wrapping around per chunk.
    d_symbol: *mut u16, // Each chunk has the amount of distinct symbols as length.
    ll_counts: *mut usize, // Precise histogram at every N symbols.
    d_counts: *mut usize // The rest can be calculated by looping through the actual symbols of this chunk.
}

// 项目: zopfli::structs::SplitCostContext
#[derive(Debug, Clone)]
pub struct SplitCostContext {
    pub lz77: *const ZopfliLZ77Store,
    pub start: usize,
    pub end: usize,
}

// 项目: zopfli::structs::SymbolStats
pub struct SymbolStats {
    /// The literal and length symbols.
    pub litlens: [usize; ZOPFLI_NUM_LL],
    /// The 32 unique dist symbols, not the 32768 possible dists.
    pub dists: [usize; ZOPFLI_NUM_D],
    /// Length of each lit/len symbol in bits.
    pub ll_symbols: [f64; ZOPFLI_NUM_LL],
    /// Length of each dist symbol in bits.
    pub d_symbols: [f64; ZOPFLI_NUM_D],
}

// 项目: zopfli::structs::RanState
#[derive(Debug, Clone)]
struct RanState {
    m_w: u32,
    m_z: u32,
}

// 项目: zopfli::structs::ZopfliHash
/// Represents a hash structure with fields for tracking hash values and occurrences.
#[repr(C)]
#[derive(Debug, Clone)]
pub struct ZopfliHash {
    /// Hash value to index of its most recent occurrence.
    pub head: *mut i32,
    /// Index to index of previous occurrence of the same hash.
    pub prev: *mut u16,
    /// Index to hash value at this index.
    pub hashval: *mut i32,
    /// Current hash value.
    pub val: i32,
    /// Hash value to index of its most recent occurrence for the second hash.
    pub head2: *mut i32,
    /// Index to index of previous occurrence of the same hash for the second hash.
    pub prev2: *mut u16,
    /// Index to hash value at this index for the second hash.
    pub hashval2: *mut i32,
    /// Current hash value for the second hash.
    pub val2: i32,
    /// Amount of repetitions of the same byte after this.
    pub same: *mut u16,
}

// 项目: zopfli::structs::Node
#[derive(Debug, Clone)]
struct Node {
    weight: usize, // Total weight (symbol count) of this chain.
    tail: Option<Box<Node>>, // Previous node(s) of this chain, or None if none.
    count: i32 // Leaf symbol index, or number of leaves before this chain.
}

// 项目: zopfli::structs::NodePool
struct NodePool {
    next: *mut Node, // Pointer to a free node in the pool. May be null.
}

// 项目: zopfli::structs::ZopfliLongestMatchCache
#[derive(Debug, Clone)]
struct ZopfliLongestMatchCache {
    length: *mut u16, // Represents a raw pointer to unsigned short
    dist: *mut u16,   // Represents a raw pointer to unsigned short
    sublen: *mut u8   // Represents a raw pointer to unsigned char
}

// 项目: zopfli::structs::ZopfliOptions
/// Options for Zopfli compression
#[derive(Debug, Clone)]
pub struct ZopfliOptions {
    /// Whether to print output
    pub verbose: i32,
    /// Whether to print more detailed output
    pub verbose_more: i32,
    /// Maximum amount of times to rerun forward and backward pass to optimize LZ77 compression cost.
    /// Good values: 10, 15 for small files, 5 for files over several MB in size or it will be too slow.
    pub num_iterations: i32,
    /// If true, splits the data in multiple deflate blocks with optimal choice for the block boundaries.
    /// Block splitting gives better compression. Default: true (1).
    pub block_splitting: i32,
    /// No longer used, left for compatibility.
    pub block_splitting_last: i32,
    /// Maximum amount of blocks to split into (0 for unlimited, but this can give extreme results
    /// that hurt compression on some files). Default value: 15.
    pub block_splitting_max: i32,
}

// 项目: zopfli::structs::ZopfliBlockState
/// Represents the state of a Zopfli block.
#[derive(Debug, Clone)]
pub struct ZopfliBlockState {
    /// Options for Zopfli compression (immutable pointer).
    pub options: *const ZopfliOptions,
    /// Cache for length/distance pairs found so far (mutable pointer).
    pub lmc: *mut ZopfliLongestMatchCache,
    /// The start (inclusive) of the current block.
    pub blockstart: usize,
    /// The end (not inclusive) of the current block.
    pub blockend: usize,
}

// 项目: zopfli::functions::ZopfliLengthLimitedCodeLengths(const size_t *, int, int, unsigned int *)
fn zopfli_length_limited_code_lengths(frequencies: *const usize, n: i32, maxbits: i32, bitlengths: *mut u32) -> i32 {
    unsafe {
        if n <= 0 || maxbits <= 0 {
            return 0;
        }

        let mut leaves: Vec<Node> = Vec::new();
        for i in 0..n {
            let freq = *frequencies.offset(i as isize);
            if freq > 0 {
                leaves.push(Node {
                    weight: freq,
                    tail: None,
                    count: i,
                });
            }
        }

        let numsymbols = leaves.len() as i32;
        if numsymbols == 0 {
            return 0;
        }
        if numsymbols == 1 {
            *bitlengths.offset(leaves[0].count as isize) = 1;
            return 0;
        }
        if numsymbols > (1 << maxbits) {
            return 1;
        }

        leaves.sort_by(|a, b| {
            let cmp_result = leaf_comparator(
                a as *const _ as *const core::ffi::c_void,
                b as *const _ as *const core::ffi::c_void,
            );
            cmp_result.cmp(&0)
        });

        let mut pool = NodePool {
            next: std::ptr::null_mut(),
        };
        let mut lists: [[*mut Node; 2]; 2] = [[std::ptr::null_mut(); 2]; 2];
        init_lists(
            &mut pool as *mut NodePool,
            leaves.as_ptr(),
            maxbits,
            lists.as_mut_ptr(),
        );

        for i in 0..maxbits {
            boundary_pm(
                lists.as_mut_ptr(),
                leaves.as_ptr(),
                numsymbols,
                &mut pool,
                i as usize,
            );
        }
        boundary_pm_final(
            lists.as_mut_ptr(),
            leaves.as_ptr(),
            numsymbols,
            &mut pool as *mut NodePool,
            maxbits as usize,
        );

        extract_bit_lengths(pool.next, leaves.as_mut_ptr(), bitlengths);

        0
    }
}

// 项目: zopfli::functions::ZopfliCalculateBitLengths(const size_t *, size_t, int, unsigned int *)
fn zopfli_calculate_bit_lengths(count: *const usize, n: usize, maxbits: i32, bitlengths: *mut u32) {
    assert!(!count.is_null(), "count pointer must not be null");
    assert!(!bitlengths.is_null(), "bitlengths pointer must not be null");

    let result = unsafe {
        zopfli_length_limited_code_lengths(
            count,
            n as i32,
            maxbits,
            bitlengths,
        )
    };

    assert!(result == 0, "ZopfliLengthLimitedCodeLengths returned an error");
}

// 项目: zopfli::functions::ZopfliLengthsToSymbols(const unsigned int *, size_t, unsigned int, unsigned int *)
pub fn zopfli_lengths_to_symbols(lengths: &[u32], n: usize, maxbits: u32, symbols: &mut [u32]) {
    assert!(symbols.len() >= n, "symbols array must have at least n elements");
    assert!(lengths.len() == n, "lengths array must have exactly n elements");

    // Step 1: Initialize symbols array to 0
    symbols.fill(0);

    // Step 2: Count the number of codes for each code length
    let mut bl_count = vec![0u32; (maxbits + 1) as usize];
    for &length in lengths {
        assert!(length <= maxbits, "length value exceeds maxbits");
        if length > 0 {
            bl_count[length as usize] += 1;
        }
    }

    // Step 3: Compute the smallest code for each code length
    let mut next_code = vec![0u32; (maxbits + 1) as usize];
    let mut code = 0;
    for bits in 1..=maxbits as usize {
        code = (code + bl_count[bits - 1]) << 1;
        next_code[bits] = code;
    }

    // Step 4: Assign codes to symbols
    for (i, &length) in lengths.iter().enumerate() {
        if length > 0 {
            symbols[i] = next_code[length as usize];
            next_code[length as usize] += 1;
        }
    }
}

// 项目: zopfli::functions::ZopfliLZ77GetByteRange(const ZopfliLZ77Store *, size_t, size_t)
fn zopfli_lz77_get_byte_range(lz77: &ZopfliLZ77Store, lstart: usize, lend: usize) -> usize {
    if lstart == lend {
        return 0;
    }

    let l = lend - 1;
    let dists = unsafe { std::slice::from_raw_parts(lz77.dists, lz77.size) };
    let litlens = unsafe { std::slice::from_raw_parts(lz77.litlens, lz77.size) };
    let pos = unsafe { std::slice::from_raw_parts(lz77.pos, lz77.size) };

    let span = if dists[l] == 0 {
        1
    } else {
        litlens[l] as usize
    };

    pos[l] + span - pos[lstart]
}

// 项目: zopfli::functions::ZopfliMaxCachedSublen(const ZopfliLongestMatchCache *, size_t, size_t)
fn zopfli_max_cached_sublen(lmc: &ZopfliLongestMatchCache, pos: usize, length: usize) -> u32 {
    unsafe {
        let sublen_start = lmc.sublen.add(pos * length);
        if *sublen_start.add(1) == 0 && *sublen_start.add(2) == 0 {
            return 0;
        }
        (*sublen_start.add(length - 1) as u32) + 3
    }
}

// 项目: zopfli::functions::ZopfliSublenToCache(const unsigned short *, size_t, size_t, ZopfliLongestMatchCache *)
fn zopfli_sublen_to_cache(sublen: &[u16], pos: usize, length: usize, lmc: &mut ZopfliLongestMatchCache) {
    if length < 3 {
        return;
    }

    unsafe {
        let cache_length = lmc.length.add(pos);
        let cache_dist = lmc.dist.add(pos);
        let cache_sublen = lmc.sublen.add(pos * ZOPFLI_CACHE_LENGTH as usize);

        let mut best_length = 0;
        let mut best_dist = 0;

        for i in 3..=length {
            let sublen_value = *sublen.get(i).unwrap_or(&0);
            if sublen_value > best_length {
                best_length = sublen_value;
                best_dist = i as u16;
            }
        }

        *cache_length = best_length;
        *cache_dist = best_dist;

        for i in 0..ZOPFLI_CACHE_LENGTH as usize {
            *cache_sublen.add(i) = if i < best_length as usize { best_dist as u8 } else { 0 };
        }
    }
}

// 项目: zopfli::functions::ZopfliCacheToSublen(const ZopfliLongestMatchCache *, size_t, size_t, unsigned short *)
fn zopfli_cache_to_sublen(lmc: &ZopfliLongestMatchCache, pos: usize, length: usize, sublen: &mut [u16]) {
    if length < 3 {
        return;
    }

    let max_cached_sublen = zopfli_max_cached_sublen(lmc, pos, length) as usize;

    unsafe {
        let sublen_ptr = lmc.sublen.add(pos * max_cached_sublen);

        let mut prevlength = 0;
        for i in 0..max_cached_sublen {
            let cached_length = *lmc.length.add(pos * max_cached_sublen + i) as usize;
            let cached_dist = *lmc.dist.add(pos * max_cached_sublen + i) as u16;

            if cached_length == 0 {
                break;
            }

            for j in prevlength..cached_length {
                if j < sublen.len() {
                    sublen[j] = cached_dist;
                }
            }

            prevlength = cached_length;

            if cached_length == max_cached_sublen {
                break;
            }
        }
    }
}

// 项目: zopfli::functions::ZopfliVerifyLenDist(const unsigned char *, size_t, size_t, unsigned short, unsigned short)
pub fn zopfli_verify_len_dist(data: Option<&[u8]>, datasize: usize, pos: usize, dist: u16, length: u16) {
    if cfg!(debug_assertions) {
        let data = data.expect("Data must be Some in debug mode");
        assert!(datasize == data.len(), "datasize must match the length of the data slice");
        assert!(pos + length as usize <= datasize, "pos + length must not exceed datasize");
        assert!(pos >= dist as usize, "pos must be greater than or equal to dist");

        for i in 0..length as usize {
            assert!(
                data[pos + i] == data[pos - dist as usize + i],
                "Data mismatch at position {}: {} != {}",
                pos + i,
                data[pos + i],
                data[pos - dist as usize + i]
            );
        }
    }
}

// 项目: zopfli::functions::ZopfliWarmupHash(const unsigned char *, size_t, size_t, ZopfliHash *)
pub fn zopfli_warmup_hash(array: *const u8, pos: usize, end: usize, h: *mut ZopfliHash) {
    unsafe {
        if array.is_null() || h.is_null() {
            return;
        }

        if pos < end {
            let byte = *array.add(pos);
            update_hash_value(h, byte);
        }

        if pos + 1 < end {
            let byte = *array.add(pos + 1);
            update_hash_value(h, byte);
        }
    }
}

// 项目: zopfli::functions::ZopfliStoreLitLenDist(unsigned short, unsigned short, size_t, ZopfliLZ77Store *)
fn zopfli_store_lit_len_dist(length: u16, dist: u16, pos: usize, store: &mut ZopfliLZ77Store) {
    assert!(length < 259, "Length must be less than 259");

    let origsize = store.size;
    let llstart = origsize / ZOPFLI_NUM_LL * ZOPFLI_NUM_LL;
    let dstart = origsize / ZOPFLI_NUM_D * ZOPFLI_NUM_D;

    if origsize % ZOPFLI_NUM_LL == 0 {
        for i in 0..ZOPFLI_NUM_LL {
            unsafe {
                *store.ll_counts.add(i) = 0;
            }
        }
        for i in llstart..origsize {
            let symbol = unsafe { *store.ll_symbol.add(i) };
            unsafe {
                *store.ll_counts.add(symbol as usize) += 1;
            }
        }
    }

    if origsize % ZOPFLI_NUM_D == 0 {
        for i in 0..ZOPFLI_NUM_D {
            unsafe {
                *store.d_counts.add(i) = 0;
            }
        }
        for i in dstart..origsize {
            let symbol = unsafe { *store.d_symbol.add(i) };
            unsafe {
                *store.d_counts.add(symbol as usize) += 1;
            }
        }
    }

    unsafe {
        *store.litlens.add(origsize) = length;
        *store.dists.add(origsize) = dist;
        *store.pos.add(origsize) = pos;
    }
    store.size += 1;

    if dist == 0 {
        unsafe {
            *store.ll_symbol.add(origsize) = length;
            *store.ll_counts.add(length as usize) += 1;
        }
    } else {
        let ll_symbol = zopfli_get_length_symbol(length as usize) as u16;
        let d_symbol = zopfli_get_dist_symbol(dist as i32) as u16;
        unsafe {
            *store.ll_symbol.add(origsize) = ll_symbol;
            *store.d_symbol.add(origsize) = d_symbol;
            *store.ll_counts.add(ll_symbol as usize) += 1;
            *store.d_counts.add(d_symbol as usize) += 1;
        }
    }
}

// 项目: zopfli::functions::ZopfliUpdateHash(const unsigned char *, size_t, size_t, ZopfliHash *)
pub fn zopfli_update_hash(array: &[u8], pos: usize, end: usize, h: &mut ZopfliHash) {
    if pos >= end {
        return;
    }

    let hpos = (pos & ZOPFLI_WINDOW_MASK) as usize;

    unsafe {
        // Update the main hash value
        update_hash_value(h, array[pos]);
        *h.hashval.add(hpos) = h.val;

        // Update the main hash table
        if *h.head.add(h.val as usize) != -1 && *h.hashval.add(*h.head.add(h.val as usize) as usize) == h.val {
            *h.prev.add(hpos) = *h.head.add(h.val as usize) as u16;
        } else {
            *h.prev.add(hpos) = hpos as u16;
        }
        *h.head.add(h.val as usize) = hpos as i32;

        // Update the same array
        let mut amount = 0;
        while pos + amount + 1 < end && amount < u16::MAX as usize && array[pos + amount] == array[pos + amount + 1] {
            amount += 1;
        }
        *h.same.add(hpos) = amount as u16;

        // Update the secondary hash value
        update_hash_value(h, array[pos]);
        *h.hashval2.add(hpos) = h.val2;

        // Update the secondary hash table
        if *h.head2.add(h.val2 as usize) != -1 && *h.hashval2.add(*h.head2.add(h.val2 as usize) as usize) == h.val2 {
            *h.prev2.add(hpos) = *h.head2.add(h.val2 as usize) as u16;
        } else {
            *h.prev2.add(hpos) = hpos as u16;
        }
        *h.head2.add(h.val2 as usize) = hpos as i32;
    }
}

// 项目: zopfli::functions::ZopfliResetHash(size_t, ZopfliHash *)
pub fn zopfli_reset_hash(window_size: usize, h: &mut ZopfliHash) {
    unsafe {
        h.val = 0;
        h.val2 = 0;

        for i in 0..window_size {
            *h.head.add(i) = -1;
            *h.head2.add(i) = -1;
        }

        for i in 0..window_size {
            *h.prev.add(i) = i as u16;
            *h.prev2.add(i) = i as u16;
        }

        for i in 0..window_size {
            *h.hashval.add(i) = -1;
            *h.hashval2.add(i) = -1;
        }

        for i in 0..window_size {
            *h.same.add(i) = 0;
        }
    }
}

// 项目: zopfli::functions::ZopfliCleanHash(ZopfliHash *)
pub fn zopfli_clean_hash(h: &mut ZopfliHash) {
    unsafe {
        if !h.head.is_null() {
            libc::free(h.head as *mut libc::c_void);
            h.head = std::ptr::null_mut();
        }
        if !h.prev.is_null() {
            libc::free(h.prev as *mut libc::c_void);
            h.prev = std::ptr::null_mut();
        }
        if !h.hashval.is_null() {
            libc::free(h.hashval as *mut libc::c_void);
            h.hashval = std::ptr::null_mut();
        }
        if !h.head2.is_null() {
            libc::free(h.head2 as *mut libc::c_void);
            h.head2 = std::ptr::null_mut();
        }
        if !h.prev2.is_null() {
            libc::free(h.prev2 as *mut libc::c_void);
            h.prev2 = std::ptr::null_mut();
        }
        if !h.hashval2.is_null() {
            libc::free(h.hashval2 as *mut libc::c_void);
            h.hashval2 = std::ptr::null_mut();
        }
        if !h.same.is_null() {
            libc::free(h.same as *mut libc::c_void);
            h.same = std::ptr::null_mut();
        }
    }
}

// 项目: zopfli::functions::ZopfliAllocHash(size_t, ZopfliHash *)
pub fn zopfli_alloc_hash(window_size: usize, h: &mut ZopfliHash) {
    unsafe {
        // Helper function to allocate memory
        unsafe fn allocate<T>(count: usize) -> *mut T {
            let layout = std::alloc::Layout::array::<T>(count).unwrap();
            let ptr = std::alloc::alloc_zeroed(layout) as *mut T;
            if ptr.is_null() {
                panic!("Memory allocation failed");
            }
            ptr
        }

        // Helper function to deallocate memory
        unsafe fn deallocate<T>(ptr: *mut T, count: usize) {
            if !ptr.is_null() {
                let layout = std::alloc::Layout::array::<T>(count).unwrap();
                std::alloc::dealloc(ptr as *mut u8, layout);
            }
        }

        // Deallocate existing memory if already allocated
        if !h.head.is_null() {
            deallocate(h.head, 65536);
        }
        if !h.prev.is_null() {
            deallocate(h.prev, window_size);
        }
        if !h.hashval.is_null() {
            deallocate(h.hashval, window_size);
        }
        if !h.head2.is_null() {
            deallocate(h.head2, 65536);
        }
        if !h.prev2.is_null() {
            deallocate(h.prev2, window_size);
        }
        if !h.hashval2.is_null() {
            deallocate(h.hashval2, window_size);
        }
        if !h.same.is_null() {
            deallocate(h.same, window_size);
        }

        // Allocate memory for each field
        h.head = allocate::<i32>(65536);
        h.prev = allocate::<u16>(window_size);
        h.hashval = allocate::<i32>(window_size);
        h.head2 = allocate::<i32>(65536);
        h.prev2 = allocate::<u16>(window_size);
        h.hashval2 = allocate::<i32>(window_size);
        h.same = allocate::<u16>(window_size);

        // Initialize val and val2 to 0
        h.val = 0;
        h.val2 = 0;
    }
}

// 项目: zopfli::functions::ZopfliCleanBlockState(ZopfliBlockState *)
pub fn zopfli_clean_block_state(s: &mut ZopfliBlockState) {
    if !s.lmc.is_null() {
        unsafe {
            zopfli_clean_cache(s.lmc);
            libc::free(s.lmc as *mut libc::c_void);
        }
        s.lmc = std::ptr::null_mut();
    }
}

// 项目: zopfli::functions::ZopfliCleanCache(ZopfliLongestMatchCache *)
fn zopfli_clean_cache(lmc: *mut ZopfliLongestMatchCache) {
    if lmc.is_null() {
        return;
    }

    unsafe {
        let cache = &mut *lmc;

        if !cache.length.is_null() {
            libc::free(cache.length as *mut libc::c_void);
            cache.length = std::ptr::null_mut();
        }

        if !cache.dist.is_null() {
            libc::free(cache.dist as *mut libc::c_void);
            cache.dist = std::ptr::null_mut();
        }

        if !cache.sublen.is_null() {
            libc::free(cache.sublen as *mut libc::c_void);
            cache.sublen = std::ptr::null_mut();
        }
    }
}

// 项目: zopfli::functions::ZopfliInitCache(size_t, ZopfliLongestMatchCache *)
fn zopfli_init_cache(blocksize: usize, lmc: &mut ZopfliLongestMatchCache) {
    const ZOPFLI_CACHE_LENGTH: usize = 256;

    // Allocate memory for length
    lmc.length = unsafe {
        let ptr = libc::malloc(blocksize * std::mem::size_of::<u16>()) as *mut u16;
        if ptr.is_null() {
            eprintln!("Failed to allocate memory for length.");
            libc::exit(libc::EXIT_FAILURE);
        }
        ptr
    };

    // Allocate memory for dist
    lmc.dist = unsafe {
        let ptr = libc::malloc(blocksize * std::mem::size_of::<u16>()) as *mut u16;
        if ptr.is_null() {
            eprintln!("Failed to allocate memory for dist.");
            libc::exit(libc::EXIT_FAILURE);
        }
        ptr
    };

    // Allocate memory for sublen
    lmc.sublen = unsafe {
        let ptr = libc::malloc(blocksize * ZOPFLI_CACHE_LENGTH * std::mem::size_of::<u8>()) as *mut u8;
        if ptr.is_null() {
            eprintln!(
                "Failed to allocate memory for sublen. Attempted size: {} bytes.",
                blocksize * ZOPFLI_CACHE_LENGTH * std::mem::size_of::<u8>()
            );
            libc::exit(libc::EXIT_FAILURE);
        }
        ptr
    };

    // Initialize length array to 1
    for i in 0..blocksize {
        unsafe {
            *lmc.length.add(i) = 1;
        }
    }

    // Initialize dist array to 0
    for i in 0..blocksize {
        unsafe {
            *lmc.dist.add(i) = 0;
        }
    }

    // Initialize sublen array to 0
    for i in 0..blocksize * ZOPFLI_CACHE_LENGTH {
        unsafe {
            *lmc.sublen.add(i) = 0;
        }
    }
}

// 项目: zopfli::functions::ZopfliCleanLZ77Store(ZopfliLZ77Store *)
fn zopfli_clean_lz77_store(store: &mut ZopfliLZ77Store) {
    unsafe {
        if !store.litlens.is_null() {
            Box::from_raw(store.litlens);
            store.litlens = std::ptr::null_mut();
        }
        if !store.dists.is_null() {
            Box::from_raw(store.dists);
            store.dists = std::ptr::null_mut();
        }
        if !store.pos.is_null() {
            Box::from_raw(store.pos);
            store.pos = std::ptr::null_mut();
        }
        if !store.ll_symbol.is_null() {
            Box::from_raw(store.ll_symbol);
            store.ll_symbol = std::ptr::null_mut();
        }
        if !store.d_symbol.is_null() {
            Box::from_raw(store.d_symbol);
            store.d_symbol = std::ptr::null_mut();
        }
        if !store.ll_counts.is_null() {
            Box::from_raw(store.ll_counts);
            store.ll_counts = std::ptr::null_mut();
        }
        if !store.d_counts.is_null() {
            Box::from_raw(store.d_counts);
            store.d_counts = std::ptr::null_mut();
        }
    }
}

// 项目: zopfli::functions::ZopfliInitLZ77Store(const unsigned char *, ZopfliLZ77Store *)
fn zopfli_init_lz77_store(data: *const u8, store: *mut ZopfliLZ77Store) {
    if store.is_null() {
        return;
    }

    unsafe {
        (*store).litlens = std::ptr::null_mut();
        (*store).dists = std::ptr::null_mut();
        (*store).size = 0;
        (*store).data = data;
        (*store).pos = std::ptr::null_mut();
        (*store).ll_symbol = std::ptr::null_mut();
        (*store).d_symbol = std::ptr::null_mut();
        (*store).ll_counts = std::ptr::null_mut();
        (*store).d_counts = std::ptr::null_mut();
    }
}

// 项目: zopfli::functions::ZopfliCalculateEntropy(const size_t *, size_t, double *)
fn zopfli_calculate_entropy(count: &[usize], n: usize, bitlengths: &mut [f64]) {
    const K_INV_LOG2: f64 = 1.0 / std::f64::consts::LN_2;

    let sum: usize = count.iter().sum();
    let log2sum = if sum == 0 {
        (n as f64).ln() * K_INV_LOG2
    } else {
        (sum as f64).ln() * K_INV_LOG2
    };

    for i in 0..n {
        if count[i] == 0 {
            bitlengths[i] = log2sum;
        } else {
            let entropy = log2sum - (count[i] as f64).ln() * K_INV_LOG2;
            bitlengths[i] = if entropy < 0.0 && entropy > -1e-5 { 0.0 } else { entropy };
        }
        assert!(bitlengths[i] >= 0.0, "Entropy value must be non-negative");
    }
}

// 项目: zopfli::functions::ZopfliCopyLZ77Store(const ZopfliLZ77Store *, ZopfliLZ77Store *)
fn zopfli_copy_lz77_store(source: &ZopfliLZ77Store, dest: &mut ZopfliLZ77Store) {
    unsafe {
        // Clean the destination store
        zopfli_clean_lz77_store(dest);

        // Initialize the destination store
        zopfli_init_lz77_store(source.data, dest);

        // Allocate and copy litlens
        dest.litlens = libc::malloc(source.size * std::mem::size_of::<u16>()) as *mut u16;
        if dest.litlens.is_null() {
            eprintln!("Failed to allocate memory for litlens");
            std::process::exit(-1);
        }
        std::ptr::copy_nonoverlapping(source.litlens, dest.litlens, source.size);

        // Allocate and copy dists
        dest.dists = libc::malloc(source.size * std::mem::size_of::<u16>()) as *mut u16;
        if dest.dists.is_null() {
            eprintln!("Failed to allocate memory for dists");
            std::process::exit(-1);
        }
        std::ptr::copy_nonoverlapping(source.dists, dest.dists, source.size);

        // Allocate and copy pos
        dest.pos = libc::malloc(source.size * std::mem::size_of::<usize>()) as *mut usize;
        if dest.pos.is_null() {
            eprintln!("Failed to allocate memory for pos");
            std::process::exit(-1);
        }
        std::ptr::copy_nonoverlapping(source.pos, dest.pos, source.size);

        // Allocate and copy ll_symbol
        let ll_symbol_size = ceil_div(source.size, 256); // Assuming 256 is the chunk size
        dest.ll_symbol = libc::malloc(ll_symbol_size * std::mem::size_of::<u16>()) as *mut u16;
        if dest.ll_symbol.is_null() {
            eprintln!("Failed to allocate memory for ll_symbol");
            std::process::exit(-1);
        }
        std::ptr::copy_nonoverlapping(source.ll_symbol, dest.ll_symbol, ll_symbol_size);

        // Allocate and copy d_symbol
        let d_symbol_size = ceil_div(source.size, 256); // Assuming 256 is the chunk size
        dest.d_symbol = libc::malloc(d_symbol_size * std::mem::size_of::<u16>()) as *mut u16;
        if dest.d_symbol.is_null() {
            eprintln!("Failed to allocate memory for d_symbol");
            std::process::exit(-1);
        }
        std::ptr::copy_nonoverlapping(source.d_symbol, dest.d_symbol, d_symbol_size);

        // Allocate and copy ll_counts
        dest.ll_counts = libc::malloc(ll_symbol_size * std::mem::size_of::<usize>()) as *mut usize;
        if dest.ll_counts.is_null() {
            eprintln!("Failed to allocate memory for ll_counts");
            std::process::exit(-1);
        }
        std::ptr::copy_nonoverlapping(source.ll_counts, dest.ll_counts, ll_symbol_size);

        // Allocate and copy d_counts
        dest.d_counts = libc::malloc(d_symbol_size * std::mem::size_of::<usize>()) as *mut usize;
        if dest.d_counts.is_null() {
            eprintln!("Failed to allocate memory for d_counts");
            std::process::exit(-1);
        }
        std::ptr::copy_nonoverlapping(source.d_counts, dest.d_counts, d_symbol_size);

        // Update the size field
        dest.size = source.size;
    }
}

// 项目: zopfli::functions::ZopfliAppendLZ77Store(const ZopfliLZ77Store *, ZopfliLZ77Store *)
fn zopfli_append_lz77_store(store: &ZopfliLZ77Store, target: &mut ZopfliLZ77Store) {
    for i in 0..store.size {
        unsafe {
            let litlen = *store.litlens.add(i);
            let dist = *store.dists.add(i);
            let pos = *store.pos.add(i);
            zopfli_store_lit_len_dist(litlen, dist, pos, target);
        }
    }
}

// 项目: zopfli::functions::ZopfliGetLengthSymbol(int)
fn zopfli_get_length_symbol(l: usize) -> i32 {
    const TABLE: [i32; 259] = [
        // Populate the table with appropriate values for length symbols.
        // This is a placeholder; replace with actual values as needed.
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25,
        26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49,
        50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73,
        74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97,
        98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117,
        118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137,
        138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157,
        158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177,
        178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197,
        198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217,
        218, 219, 220, 221, 222, 223, 224, 225, 226, 227, 228, 229, 230, 231, 232, 233, 234, 235, 236, 237,
        238, 239, 240, 241, 242, 243, 244, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 255, 256, 257,
        258,
    ];
    if l <= 258 {
        TABLE[l]
    } else {
        panic!("Input length out of range: {}", l);
    }
}

// 项目: zopfli::functions::ZopfliGetDistSymbol(int)
pub fn zopfli_get_dist_symbol(dist: i32) -> i32 {
    if dist < 5 {
        return dist - 1;
    }
    let dist_minus_one = dist - 1;
    let l = 31 - dist_minus_one.leading_zeros() as i32;
    let r = (dist_minus_one >> (l - 1)) & 1;
    l * 2 + r
}

// 项目: zopfli::functions::AbsDiff(size_t, size_t)
fn abs_diff(x: usize, y: usize) -> usize {
    if x > y {
        x - y
    } else {
        y - x
    }
}

// 项目: zopfli::functions::OptimizeHuffmanForRle(int, size_t *)
fn optimize_huffman_for_rle(length: i32, counts: &mut Vec<usize>) {
    if length <= 0 || counts.is_empty() {
        return;
    }

    // Step 1: Trim trailing zeros
    let mut max_non_zero_index = 0;
    for i in 0..length as usize {
        if counts[i] != 0 {
            max_non_zero_index = i;
        }
    }
    counts.truncate(max_non_zero_index + 1);

    // Step 2: Mark regions suitable for RLE
    let mut good_for_rle = vec![false; counts.len()];
    let mut symbol = counts[0];
    let mut start = 0;

    for i in 1..=counts.len() {
        if i == counts.len() || counts[i] != symbol {
            let length = i - start;
            if (symbol == 0 && length >= 5) || (symbol != 0 && length >= 7) {
                for j in start..i {
                    good_for_rle[j] = true;
                }
            }
            if i < counts.len() {
                symbol = counts[i];
            }
            start = i;
        }
    }

    // Step 3: Adjust counts for RLE optimization
    let mut i = 0;
    while i < counts.len() {
        if !good_for_rle[i] {
            i += 1;
            continue;
        }

        let mut sum = counts[i];
        let mut start = i;
        let mut end = i + 1;

        while end < counts.len() && good_for_rle[end] {
            sum += counts[end];
            end += 1;
        }

        let count = sum / (end - start);
        let remainder = sum % (end - start);

        for j in start..end {
            counts[j] = count + if j - start < remainder { 1 } else { 0 };
        }

        i = end;
    }
}

// 项目: zopfli::functions::ZopfliGetDistSymbolExtraBits(int)
fn zopfli_get_dist_symbol_extra_bits(s: usize) -> i32 {
    const TABLE: [i32; 30] = [
        0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 
        7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13,
    ];
    TABLE.get(s).copied().unwrap_or_else(|| panic!("Index out of range: {}", s))
}

// 项目: zopfli::functions::ZopfliGetLengthSymbolExtraBits(int)
fn zopfli_get_length_symbol_extra_bits(s: i32) -> i32 {
    const EXTRA_BITS_TABLE: [i32; 29] = [
        0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0, 0, 0, 0, 0,
    ];
    if s < 257 || s > 285 {
        panic!("Input symbol out of range: {}", s);
    }
    EXTRA_BITS_TABLE[(s - 257) as usize]
}

// 项目: zopfli::functions::LeafComparator(const void *, const void *)
fn leaf_comparator(a: *const core::ffi::c_void, b: *const core::ffi::c_void) -> i32 {
    let node_a = unsafe { &*(a as *const Node) };
    let node_b = unsafe { &*(b as *const Node) };
    node_a.weight.cmp(&node_b.weight) as i32
}

// 项目: zopfli::functions::ExtractBitLengths(Node *, Node *, unsigned int *)
unsafe fn extract_bit_lengths(chain: *mut Node, leaves: *mut Node, bitlengths: *mut u32) {
    let mut counts = [0; 16];
    let mut ptr = chain;

    // Traverse the chain and populate counts array
    while !ptr.is_null() {
        let node = &*ptr;
        let weight = node.weight;
        if weight < counts.len() {
            counts[weight] += 1;
        }
        ptr = match &node.tail {
            Some(tail) => &**tail as *const Node as *mut Node,
            None => std::ptr::null_mut(),
        };
    }

    let mut val = counts.len() as i32 - 1;
    let mut value = 0;
    let mut ptr = leaves;

    // Calculate bit lengths
    while val >= 0 {
        for _ in 0..counts[val as usize] {
            if ptr.is_null() {
                return; // Safety check: Ensure ptr is valid
            }
            let leaf = &mut *ptr;
            if leaf.count >= 0 {
                *bitlengths.add(leaf.count as usize) = value;
            }
            ptr = match &leaf.tail {
                Some(tail) => &**tail as *const Node as *mut Node,
                None => std::ptr::null_mut(),
            };
        }
        val -= 1;
        value += 1;
    }
}

// 项目: zopfli::functions::InitNode(size_t, int, Node *, Node *)
fn init_node(weight: usize, count: i32, tail: Option<Box<Node>>, node: &mut Node) {
    node.weight = weight;
    node.count = count;
    node.tail = tail;
}

// 项目: zopfli::functions::InitLists(NodePool *, const Node *, int, Node *(*)[2])
fn init_lists(pool: *mut NodePool, leaves: *const Node, maxbits: i32, lists: *mut [*mut Node; 2]) {
    unsafe {
        if pool.is_null() || leaves.is_null() || lists.is_null() || maxbits <= 0 {
            return;
        }

        let pool_ref = &mut *pool;

        // Allocate two new nodes from the pool
        let node0 = pool_ref.next;
        if node0.is_null() {
            return;
        }
        pool_ref.next = node0.add(1);

        let node1 = pool_ref.next;
        if node1.is_null() {
            return;
        }
        pool_ref.next = node1.add(1);

        // Initialize the nodes
        init_node((*leaves).weight, 1, None, &mut *node0);
        init_node((*leaves.add(1)).weight, 1, None, &mut *node1);

        // Populate the lists array
        for i in 0..maxbits {
            let list_row = &mut *lists.add(i as usize);
            list_row[0] = node0;
            list_row[1] = node1;
        }
    }
}

// 项目: zopfli::functions::BoundaryPMFinal(Node *(*)[2], Node *, int, NodePool *, int)
fn boundary_pm_final(lists: *mut [*mut Node; 2], leaves: *const Node, numsymbols: i32, pool: *mut NodePool, index: usize) {
    unsafe {
        if lists.is_null() || leaves.is_null() || pool.is_null() {
            return;
        }

        let current_list = lists.add(index);
        let prev_list = if index > 0 { lists.add(index - 1) } else { std::ptr::null_mut() };

        let last_node = (*current_list)[1];
        if last_node.is_null() {
            return;
        }

        let lastcount = (*last_node).count;
        if lastcount < 0 || lastcount >= numsymbols {
            return;
        }

        let sum = if !prev_list.is_null() {
            let prev_tail_0 = (*prev_list)[0];
            let prev_tail_1 = (*prev_list)[1];
            let weight_0 = if !prev_tail_0.is_null() { (*prev_tail_0).weight } else { 0 };
            let weight_1 = if !prev_tail_1.is_null() { (*prev_tail_1).weight } else { 0 };
            weight_0 + weight_1
        } else {
            0
        };

        let leaf_weight = (*leaves.add(lastcount as usize)).weight;

        if sum > leaf_weight {
            let newchain = (*pool).next;
            if newchain.is_null() {
                return;
            }

            (*pool).next = if let Some(tail) = (*newchain).tail.take() {
                Box::into_raw(tail)
            } else {
                std::ptr::null_mut()
            };

            (*newchain).count = lastcount + 1;
            (*newchain).weight = leaf_weight;
            (*newchain).tail = Some(Box::from_raw(last_node));

            (*current_list)[1] = newchain;
        } else {
            (*current_list)[1] = if !prev_list.is_null() { (*prev_list)[1] } else { std::ptr::null_mut() };
        }
    }
}

// 项目: zopfli::functions::BoundaryPM(Node *(*)[2], Node *, int, NodePool *, int)
fn boundary_pm(lists: *mut [*mut Node; 2], leaves: *const Node, numsymbols: i32, pool: &mut NodePool, index: usize) {
    if lists.is_null() || leaves.is_null() || pool.next.is_null() {
        return;
    }

    unsafe {
        let lists = &mut *lists;
        let last_node = (*lists)[1];

        if index == 0 && !last_node.is_null() && (*last_node).count >= numsymbols {
            return;
        }

        let new_node = pool.next;
        pool.next = if let Some(tail) = (*new_node).tail.as_mut() {
            tail.as_mut()
        } else {
            std::ptr::null_mut()
        };

        if index == 0 {
            let leaf = leaves.add((*new_node).count as usize);
            (*new_node).weight = (*leaf).weight;
            (*new_node).count += 1;
            (*new_node).tail = Some(Box::new((*leaf).clone()));
            (*lists)[1] = new_node;
            return;
        }

        let prev_list = (*lists)[0];
        if prev_list.is_null() {
            return;
        }

        let prev1 = prev_list;
        let prev2 = if let Some(tail) = (*prev1).tail.as_mut() {
            tail.as_mut()
        } else {
            std::ptr::null_mut()
        };

        if prev2.is_null() || ((*prev1).weight + (*prev2).weight > (*leaves.add((*new_node).count as usize)).weight
            && (*new_node).count < numsymbols)
        {
            let leaf = leaves.add((*new_node).count as usize);
            (*new_node).weight = (*leaf).weight;
            (*new_node).count += 1;
            (*new_node).tail = Some(Box::new((*leaf).clone()));
            (*lists)[1] = new_node;
            boundary_pm(lists, leaves, numsymbols, pool, index);
        } else {
            (*new_node).weight = (*prev1).weight + (*prev2).weight;
            (*new_node).count = (*prev1).count + (*prev2).count;
            (*new_node).tail = Some(Box::new((*prev1).clone()));
            (*lists)[1] = new_node;

            (*lists)[0] = if let Some(tail) = (*prev1).tail.as_mut() {
                tail.as_mut()
            } else {
                std::ptr::null_mut()
            };
            boundary_pm(lists, leaves, numsymbols, pool, index - 1);

            (*lists)[0] = prev2;
            boundary_pm(lists, leaves, numsymbols, pool, index - 1);
        }
    }
}

// 项目: zopfli::functions::AddHuffmanBits(unsigned int, unsigned int, unsigned char *, unsigned char **, size_t *)
fn add_huffman_bits(symbol: u32, length: u32, bp: &mut u8, out: &mut Vec<u8>, outsize: &mut usize) {
    for i in 0..length {
        let bit = (symbol >> (length - 1 - i)) & 1;
        if *bp == 0 {
            out.push(0);
            *outsize += 1;
        }
        out.last_mut().map(|byte| *byte |= (bit as u8) << *bp);
        *bp += 1;
        if *bp == 8 {
            *bp = 0;
        }
    }
}

// 项目: zopfli::functions::AddBits(unsigned int, unsigned int, unsigned char *, unsigned char **, size_t *)
pub fn add_bits(symbol: u32, length: u32, bp: &mut u8, out: &mut Vec<u8>, outsize: &mut usize) {
    for i in 0..length {
        let bit = (symbol >> i) & 1; // Extract the i-th bit from the symbol
        if *bp == 0 {
            out.push(0); // Add a new byte to the output buffer
            *outsize += 1;
        }
        let last_byte_index = out.len() - 1;
        out[last_byte_index] |= (bit as u8) << *bp; // Write the bit to the current position
        *bp += 1;
        if *bp > 7 {
            *bp = 0; // Reset bit pointer after filling a byte
        }
    }
}

// 项目: zopfli::functions::PatchDistanceCodesForBuggyDecoders(unsigned int *)
fn patch_distance_codes_for_buggy_decoders(d_lengths: &mut [u32; 30]) {
    let non_zero_count = d_lengths.iter().filter(|&&len| len > 0).count();

    match non_zero_count {
        0 => {
            d_lengths[0] = 1;
            d_lengths[1] = 1;
        }
        1 => {
            if d_lengths[0] > 0 {
                d_lengths[1] = 1;
            } else {
                d_lengths[0] = 1;
            }
        }
        _ => {}
    }
}

// 项目: zopfli::functions::GetFixedTree(unsigned int *, unsigned int *)
fn get_fixed_tree(ll_lengths: &mut [u32; 288], d_lengths: &mut [u32; 32]) {
    for i in 0..144 {
        ll_lengths[i] = 8;
    }
    for i in 144..256 {
        ll_lengths[i] = 9;
    }
    for i in 256..280 {
        ll_lengths[i] = 7;
    }
    for i in 280..288 {
        ll_lengths[i] = 8;
    }
    for i in 0..32 {
        d_lengths[i] = 5;
    }
}

// 项目: zopfli::functions::ZopfliGetDistExtraBits(int)
pub fn zopfli_get_dist_extra_bits(dist: i32) -> i32 {
    if dist < 5 {
        return 0;
    }
    let dist_minus_one = dist - 1;
    let leading_zeros = dist_minus_one.leading_zeros();
    let log2_dist_minus_one = 31 - leading_zeros;
    (log2_dist_minus_one - 1) as i32
}

// 项目: zopfli::functions::AddBit(int, unsigned char *, unsigned char **, size_t *)
pub fn add_bit(bit: i32, bp: &mut u8, out: &mut Vec<u8>, outsize: &mut usize) {
    if *bp == 0 {
        out.push(0);
        *outsize += 1;
    }
    if let Some(last_byte) = out.last_mut() {
        *last_byte |= (bit as u8) << *bp;
    }
    *bp = (*bp + 1) % 8;
}

// 项目: zopfli::functions::ZopfliGetDistExtraBitsValue(int)
pub fn zopfli_get_dist_extra_bits_value(dist: i32) -> i32 {
    if dist < 5 {
        return 0;
    }
    let l = 31 - (dist - 1).leading_zeros() as i32;
    let offset = (1 << l) - 1;
    let extra_bits = dist - 1 - offset;
    extra_bits
}

// 项目: zopfli::functions::GetMatch(const unsigned char *, const unsigned char *, const unsigned char *, const unsigned char *)
pub fn get_match(scan: *const u8, match_: *const u8, end: *const u8, safe_end: *const u8) -> *const u8 {
    unsafe {
        let mut scan = scan;
        let mut match_ = match_;

        // Ensure pointers are valid and within bounds
        while scan < safe_end && scan < end && match_ < end {
            // Compare in chunks of 8 bytes if possible
            if (scan as usize) % 8 == 0 && (match_ as usize) % 8 == 0 && safe_end as usize - scan as usize >= 8 {
                let scan_chunk = *(scan as *const u64);
                let match_chunk = *(match_ as *const u64);
                if scan_chunk != match_chunk {
                    // Find the first mismatched byte in the chunk
                    for i in 0..8 {
                        if *scan.add(i) != *match_.add(i) {
                            return scan.add(i);
                        }
                    }
                }
                scan = scan.add(8);
                match_ = match_.add(8);
            } else if (scan as usize) % 4 == 0 && (match_ as usize) % 4 == 0 && safe_end as usize - scan as usize >= 4 {
                // Compare in chunks of 4 bytes if possible
                let scan_chunk = *(scan as *const u32);
                let match_chunk = *(match_ as *const u32);
                if scan_chunk != match_chunk {
                    // Find the first mismatched byte in the chunk
                    for i in 0..4 {
                        if *scan.add(i) != *match_.add(i) {
                            return scan.add(i);
                        }
                    }
                }
                scan = scan.add(4);
                match_ = match_.add(4);
            } else {
                // Compare byte by byte
                if *scan != *match_ {
                    return scan;
                }
                scan = scan.add(1);
                match_ = match_.add(1);
            }
        }

        // Handle remaining bytes if any
        while scan < end && match_ < end {
            if *scan != *match_ {
                return scan;
            }
            scan = scan.add(1);
            match_ = match_.add(1);
        }

        scan
    }
}

// 项目: zopfli::functions::UpdateHashValue(ZopfliHash *, unsigned char)
fn update_hash_value(h: *mut ZopfliHash, c: u8) {
    unsafe {
        if h.is_null() {
            return;
        }
        let hash = &mut *h;
        hash.val = ((((hash.val as u32) << HASH_SHIFT) ^ (c as u32)) & HASH_MASK) as i32;
    }
}

// 项目: zopfli::functions::TraceBackwards(size_t, const unsigned short *, unsigned short **, size_t *)
pub fn trace_backwards(size: usize, length_array: &[u16], path: &mut *mut u16, pathsize: &mut usize) {
    if size == 0 {
        *pathsize = 0;
        return;
    }

    let mut current_index = size;
    let mut temp_path = Vec::new();

    while current_index > 0 {
        let length = length_array[current_index - 1] as usize;
        assert!(length > 0, "Length value must not be zero");
        assert!(length <= current_index, "Length value exceeds current index");
        assert!(length <= size, "Length value exceeds maximum size");

        temp_path.push(length as u16);
        current_index -= length;
    }

    temp_path.reverse();
    *pathsize = temp_path.len();

    unsafe {
        let path_ptr = *path;
        for (i, &value) in temp_path.iter().enumerate() {
            *path_ptr.add(i) = value;
        }
    }
}

// 项目: zopfli::functions::zopfli_min(size_t, size_t)
fn zopfli_min(a: usize, b: usize) -> usize {
    if a < b { a } else { b }
}

// 项目: zopfli::functions::GetCostModelMinCost(CostModelFun *, void *)
fn get_cost_model_min_cost(
    costmodel: fn(u16, u16, Option<*mut core::ffi::c_void>) -> f64,
    costcontext: Option<*mut core::ffi::c_void>,
) -> f64 {
    const ZOPFLI_LARGE_FLOAT: f64 = f64::MAX;
    const MIN_LENGTH: u16 = 3;
    const MAX_LENGTH: u16 = 258;
    const DSYMBOLS: [u16; 30] = [
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30,
    ];

    let mut min_cost = ZOPFLI_LARGE_FLOAT;
    let mut best_length = MIN_LENGTH;
    let mut best_distance = DSYMBOLS[0];

    // Find the minimum cost for lengths
    for length in MIN_LENGTH..=MAX_LENGTH {
        let cost = costmodel(length, 0, costcontext);
        if cost < min_cost {
            min_cost = cost;
            best_length = length;
        }
    }

    // Find the minimum cost for distances
    for &distance in DSYMBOLS.iter() {
        let cost = costmodel(MIN_LENGTH, distance, costcontext);
        if cost < min_cost {
            min_cost = cost;
            best_distance = distance;
        }
    }

    // Return the cost for the best length and distance
    costmodel(best_length, best_distance, costcontext)
}

// 项目: zopfli::functions::GetLengthScore(int, int)
pub fn get_length_score(length: i32, distance: i32) -> i32 {
    if distance > 1024 {
        length - 1
    } else {
        length
    }
}

// 项目: zopfli::functions::CalculateStatistics(SymbolStats *)
fn calculate_statistics(stats: &mut SymbolStats) {
    zopfli_calculate_entropy(&stats.litlens, stats.litlens.len(), &mut stats.ll_symbols);
    zopfli_calculate_entropy(&stats.dists, stats.dists.len(), &mut stats.d_symbols);
}

// 项目: zopfli::functions::GetStatistics(const ZopfliLZ77Store *, SymbolStats *)
pub fn get_statistics(store: &ZopfliLZ77Store, stats: &mut SymbolStats) {
    // Reset statistics
    stats.litlens.fill(0);
    stats.dists.fill(0);

    // Iterate through the LZ77 store
    for i in 0..store.size {
        unsafe {
            let litlen = *store.litlens.add(i);
            let dist = *store.dists.add(i);

            if dist == 0 {
                // Literal symbol
                stats.litlens[litlen as usize] += 1;
            } else {
                // Length and distance symbols
                let length_symbol = zopfli_get_length_symbol(litlen as usize);
                let dist_symbol = zopfli_get_dist_symbol(dist as i32);

                stats.litlens[length_symbol as usize] += 1;
                stats.dists[dist_symbol as usize] += 1;
            }
        }
    }

    // Add the end symbol (256)
    stats.litlens[256] = 1;

    // Calculate entropy and other statistics
    calculate_statistics(stats);
}

// 项目: zopfli::functions::ClearStatFreqs(SymbolStats *)
pub fn clear_stat_freqs(stats: &mut SymbolStats) {
    for i in 0..ZOPFLI_NUM_LL {
        stats.litlens[i] = 0;
    }
    for i in 0..ZOPFLI_NUM_D {
        stats.dists[i] = 0;
    }
}

// 项目: zopfli::functions::Ran(RanState *)
fn ran(state: &mut RanState) -> u32 {
    state.m_z = 36969 * (state.m_z & 65535) + (state.m_z >> 16);
    state.m_w = 18000 * (state.m_w & 65535) + (state.m_w >> 16);
    ((state.m_z as u32) << 16) + (state.m_w as u32)
}

// 项目: zopfli::functions::RandomizeFreqs(RanState *, size_t *, int)
fn randomize_freqs(state: &mut RanState, freqs: &mut [usize], n: i32) {
    if n <= 0 || freqs.is_empty() {
        return;
    }

    let len = freqs.len();
    for i in 0..n as usize {
        if i >= len {
            break;
        }

        let random_value = ran(state) >> 4;
        if random_value % 3 == 0 {
            let random_index = (ran(state) % n as u32) as usize;
            if random_index < len {
                freqs[i] = freqs[random_index];
            }
        }
    }
}

// 项目: zopfli::functions::RandomizeStatFreqs(RanState *, SymbolStats *)
pub fn randomize_stat_freqs(state: &mut RanState, stats: &mut SymbolStats) {
    randomize_freqs(state, &mut stats.litlens, ZOPFLI_NUM_LL as i32);
    randomize_freqs(state, &mut stats.dists, ZOPFLI_NUM_D as i32);
    stats.litlens[256] = 1; // Ensure the end symbol frequency is set to 1
}

// 项目: zopfli::functions::InitRanState(RanState *)
fn init_ran_state(state: &mut RanState) {
    state.m_w = 1;
    state.m_z = 2;
}

// 项目: zopfli::functions::AddWeighedStatFreqs(const SymbolStats *, double, const SymbolStats *, double, SymbolStats *)
fn add_weighed_stat_freqs(stats1: &SymbolStats, w1: f64, stats2: &SymbolStats, w2: f64, result: &mut SymbolStats) {

    for i in 0..ZOPFLI_NUM_LL {
        result.litlens[i] = ((stats1.litlens[i] as f64 * w1) + (stats2.litlens[i] as f64 * w2)) as usize;
    }
    for i in 0..ZOPFLI_NUM_D {
        result.dists[i] = ((stats1.dists[i] as f64 * w1) + (stats2.dists[i] as f64 * w2)) as usize;
    }
    result.litlens[256] = 1;

}

// 项目: zopfli::functions::CeilDiv(size_t, size_t)
pub fn ceil_div(a: usize, b: usize) -> usize {
    assert!(b != 0, "Division by zero is not allowed");
    (a + b - 1) / b
}

// 项目: zopfli::functions::CopyStats(SymbolStats *, SymbolStats *)
pub fn copy_stats(source: &SymbolStats, dest: &mut SymbolStats) {
    dest.litlens.copy_from_slice(&source.litlens);
    dest.dists.copy_from_slice(&source.dists);
    dest.ll_symbols.copy_from_slice(&source.ll_symbols);
    dest.d_symbols.copy_from_slice(&source.d_symbols);
}

// 项目: zopfli::functions::InitStats(SymbolStats *)
pub fn init_stats(stats: &mut SymbolStats) {
    stats.litlens.fill(0);
    stats.dists.fill(0);
    stats.ll_symbols.fill(0.0);
    stats.d_symbols.fill(0.0);
}

// 项目: zopfli::functions::FindLargestSplittableBlock(size_t, const unsigned char *, const size_t *, size_t, size_t *, size_t *)
fn find_largest_splittable_block(lz77size: usize, done: *const u8, splitpoints: *const usize, npoints: usize, lstart: *mut usize, lend: *mut usize) -> i32 {

    if done.is_null() || splitpoints.is_null() || lstart.is_null() || lend.is_null() {
        return 0; // Invalid input pointers
    }

    let mut max_length = 0;
    let mut found = 0;

    unsafe {
        let splitpoints_slice = std::slice::from_raw_parts(splitpoints, npoints);
        let done_slice = std::slice::from_raw_parts(done, lz77size);

        for i in 0..=npoints {
            let start = if i == 0 { 0 } else { splitpoints_slice[i - 1] };
            let end = if i == npoints { lz77size } else { splitpoints_slice[i] };

            if start >= lz77size || end > lz77size || start >= end {
                continue; // Skip invalid ranges
            }

            if done_slice[start] == 0 {
                let length = end - start;
                if length > max_length {
                    max_length = length;
                    *lstart = start;
                    *lend = end;
                    found = 1;
                }
            }
        }
    }

    found
}

// 项目: zopfli::functions::PrintBlockSplitPoints(const ZopfliLZ77Store *, const size_t *, size_t)
fn print_block_split_points(lz77: &ZopfliLZ77Store, lz77splitpoints: *const usize, nlz77points: usize) {
    use std::ptr;
    use std::io::{self, Write};

    assert!(!lz77splitpoints.is_null(), "lz77splitpoints pointer is null");

    let mut uncompressed_points = Vec::with_capacity(nlz77points);
    let mut current_uncompressed_index = 0;

    for i in 0..lz77.size {
        let litlen = unsafe { *lz77.litlens.add(i) };
        let dist = unsafe { *lz77.dists.add(i) };

        if dist == 0 {
            // Literal, just move forward by 1
            current_uncompressed_index += 1;
        } else {
            // Length-distance pair, move forward by the length
            current_uncompressed_index += litlen as usize;
        }

        // Check if the current index matches any split point
        for j in 0..nlz77points {
            let split_point = unsafe { *lz77splitpoints.add(j) };
            if split_point == i {
                uncompressed_points.push(current_uncompressed_index);
                break;
            }
        }
    }

    assert!(
        uncompressed_points.len() == nlz77points,
        "Mismatch between calculated and expected split points"
    );

    let stderr = io::stderr();
    let mut handle = stderr.lock();
    for point in uncompressed_points {
        writeln!(handle, "Uncompressed split point: {} (0x{:X})", point, point).unwrap();
    }
}

// 项目: zopfli::functions::AddSorted(size_t, size_t **, size_t *)
unsafe fn add_sorted(value: usize, out: *mut *mut usize, outsize: *mut usize) {
    if out.is_null() || outsize.is_null() {
        return;
    }

    let size = *outsize;
    let array = *out;

    // Allocate new memory for the array with an extra slot for the new value
    let new_size = size + 1;
    let new_array = libc::malloc(new_size * std::mem::size_of::<usize>()) as *mut usize;
    if new_array.is_null() {
        return;
    }

    // Copy existing elements to the new array
    for i in 0..size {
        *new_array.add(i) = *array.add(i);
    }

    // Insert the new value in sorted order
    let mut inserted = false;
    for i in 0..size {
        if !inserted && *new_array.add(i) > value {
            // Shift elements to the right
            for j in (i..size).rev() {
                *new_array.add(j + 1) = *new_array.add(j);
            }
            *new_array.add(i) = value;
            inserted = true;
            break;
        }
    }

    // If the value is larger than all existing elements, append it at the end
    if !inserted {
        *new_array.add(size) = value;
    }

    // Free the old array and update the pointers
    libc::free(array as *mut libc::c_void);
    *out = new_array;
    *outsize = new_size;
}

// 项目: zopfli::functions::FindMinimum(FindMinimumFun, void *, size_t, size_t, double *)
fn find_minimum(
    f: fn(*mut core::ffi::c_void, usize) -> f64,
    context: *mut core::ffi::c_void,
    start: usize,
    end: usize,
    smallest: &mut f64,
) -> usize {
    const NUM: usize = 9;

    if end <= start {
        panic!("Invalid range: start must be less than end");
    }

    if end - start < 1024 {
        let mut min_index = start;
        *smallest = f(context, start);
        for i in start + 1..end {
            let value = f(context, i);
            if value < *smallest {
                *smallest = value;
                min_index = i;
            }
        }
        return min_index;
    }

    let mut current_start = start;
    let mut current_end = end;
    let mut previous_smallest = f64::MAX;
    let mut min_index = start;

    loop {
        let step = (current_end - current_start) / (NUM + 1);
        let mut local_smallest = f64::MAX;
        let mut local_min_index = current_start;

        for i in 0..=NUM {
            let index = current_start + i * step;
            if index >= current_end {
                break;
            }
            let value = f(context, index);
            if value < local_smallest {
                local_smallest = value;
                local_min_index = index;
            }
        }

        if local_smallest >= previous_smallest {
            break;
        }

        previous_smallest = local_smallest;
        min_index = local_min_index;

        let left_bound = if min_index > step { min_index - step } else { current_start };
        let right_bound = if min_index + step < current_end {
            min_index + step
        } else {
            current_end
        };

        current_start = left_bound;
        current_end = right_bound;

        if current_end - current_start < 1024 {
            for i in current_start..current_end {
                let value = f(context, i);
                if value < previous_smallest {
                    previous_smallest = value;
                    min_index = i;
                }
            }
            break;
        }
    }

    *smallest = previous_smallest;
    min_index
}

// ================ 当前验证的函数实现 ================

pub fn calculate_block_symbol_size_small(
    ll_lengths: &[u32],
    d_lengths: &[u32],
    lz77: &ZopfliLZ77Store,
    lstart: usize,
    lend: usize,
) -> usize {
    assert!(lend <= lz77.litlens.len());
    assert!(lend <= lz77.dists.len());
    assert!(lstart <= lend);

    let mut result = 0;

    for i in lstart..lend {
        let litlen = lz77.litlens[i] as usize;
        let dist = lz77.dists[i] as i32;

        if dist == 0 {
            // Literal value
            assert!(litlen < 259);
            result += ll_lengths[litlen] as usize;
        } else {
            // Length/Distance pair
            let length_symbol = zopfli_get_length_symbol(litlen);
            let dist_symbol = zopfli_get_dist_symbol(dist);

            result += ll_lengths[length_symbol as usize] as usize;
            result += d_lengths[dist_symbol as usize] as usize;

            let length_extra_bits = zopfli_get_length_symbol_extra_bits(length_symbol);
            let dist_extra_bits = zopfli_get_dist_symbol_extra_bits(dist_symbol as usize);

            result += length_extra_bits as usize;
            result += dist_extra_bits as usize;
        }
    }

    // Add the end-of-block symbol (256)
    result += ll_lengths[256] as usize;

    result
}