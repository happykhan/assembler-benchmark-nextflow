class BenchmarkUtils {
    static String shellQuote(value) {
        "'" + value.toString().replace("'", "'\"'\"'") + "'"
    }
    static List sourcesUnder(project, List directories) {
        def names = []
        directories.each { name ->
            new File(project.toString(), name).eachFileRecurse { item ->
                def relative = new File(project.toString()).toPath().relativize(item.toPath()).toString()
                if (item.isFile() && !relative.contains('__pycache__') && !relative.contains('node_modules') && !relative.contains('.DS_Store')) names << relative
            }
        }
        names.sort()
    }
    static String sourceHash(project, List names) {
        def digest = java.security.MessageDigest.getInstance('SHA-256')
        (names + ['environments/pixi.toml', 'environments/pixi.lock', 'bin/bench-run']).unique().sort().each { name ->
            digest.update(name.getBytes('UTF-8'))
            digest.update(new File(project.toString(), name).bytes)
        }
        digest.digest().encodeHex().toString()
    }
}
