from conans import ConanFile, AutoToolsBuildEnvironment, tools
from conans.errors import ConanInvalidConfiguration
import os
import glob


class LibpqConan(ConanFile):
    name = "postgreSQL"
    version = "0.0.1"
    description = "The library used by all the standard PostgreSQL tools."
    topics = ("conan", "libpq", "postgresql", "database", "db")
    url = "https://github.com/elear-solutions/postgres"
    license = "PostgreSQL"
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        "with_zlib": [True, False, "deprecated"],
        "with_openssl": [True, False],
        "disable_rpath": [True, False]
    }
    default_options = {
        'shared': False,
        'fPIC': True,
        'with_zlib': "deprecated",
        'with_openssl': False,
        'disable_rpath': False
    }
    default_user = "jenkins"
    default_channel = "master"
    _autotools = None

    def build_requirements(self):
        if self.settings.compiler == "Visual Studio":
            self.build_requires("strawberryperl/5.30.0.1")
        elif tools.os_info.is_windows:
            if "CONAN_BASH_PATH" not in os.environ and tools.os_info.detect_windows_subsystem() != 'msys2':
                self.build_requires("msys2/20190524")
    @property
    def _source_subfolder(self):
        return ".."

    @property
    def _is_clang8_x86(self):
        return self.settings.os == "Linux" and \
               self.settings.compiler == "clang" and \
               self.settings.compiler.version == "8" and \
               self.settings.arch == "x86"

    def configure(self):
        del self.settings.compiler.libcxx
        del self.settings.compiler.cppstd

        if self.settings.compiler != "Visual Studio" and self.settings.os == "Windows":
            if self.options.shared:
                raise ConanInvalidConfiguration("static mingw build is not possible")
        # Looking into source code, it appears that zlib is not used in libpq
        if self.options.with_zlib != "deprecated":
            self.output.warn("with_zlib option is deprecated, do not use anymore")
        del self.options.with_zlib

    def requirements(self):
        if self.options.with_openssl:
            self.requires("openssl/1.1.1h")
        if self.user and self.channel:
            default_user = self.user
            default_channel = self.channel
        self.requires("bison/[~0.0.1]@%s/%s" % (default_user, default_channel))

    def source(self):
        tools.get(**self.conan_data["sources"][self.version])
        extracted_dir = "postgresql-" + self.version
        os.rename(extracted_dir, self._source_subfolder)

    def _configure_autotools(self):
        if not self._autotools:
            self._autotools = AutoToolsBuildEnvironment(self, win_bash=tools.os_info.is_windows)
            args = ['--without-readline']
            args.append('--without-zlib')
            args.append('--with-openssl' if self.options.with_openssl else '--without-openssl')
            if tools.cross_building(self.settings) and not self.options.with_openssl:
                args.append("--disable-strong-random")
            if tools.cross_building(self.settings):
                args.append("USE_DEV_URANDOM=1")
            if self.settings.os != "Windows" and self.options.disable_rpath:
                args.append('--disable-rpath')
            if self._is_clang8_x86:
                self._autotools.flags.append("-msse2")
            with tools.chdir(".."):
                self._autotools.configure(args=args)
        return self._autotools

    @property
    def _make_args(self):
        args = []
        if self.settings.os == "Windows":
            args.append("MAKE_DLL={}".format(str(self.options.shared).lower()))
        return args

    def build(self):
        if self.settings.compiler == "Visual Studio":
            # https://www.postgresql.org/docs/8.3/install-win32-libpq.html
            # https://github.com/postgres/postgres/blob/master/src/tools/msvc/README
            if not self.options.shared:
                tools.replace_in_file(os.path.join(self._source_subfolder, "src", "tools", "msvc", "MKvcbuild.pm"),
                                      "$libpq = $solution->AddProject('libpq', 'dll', 'interfaces',",
                                      "$libpq = $solution->AddProject('libpq', 'lib', 'interfaces',")
            system_libs = ", ".join(["'{}.lib'".format(lib) for lib in self.deps_cpp_info.system_libs])
            tools.replace_in_file(os.path.join(self._source_subfolder, "src", "tools", "msvc", "Project.pm"),
                                  "libraries             => [],",
                                  "libraries             => [{}],".format(system_libs))
            runtime = {'MT': 'MultiThreaded',
                       'MTd': 'MultiThreadedDebug',
                       'MD': 'MultiThreadedDLL',
                       'MDd': 'MultiThreadedDebugDLL'}.get(str(self.settings.compiler.runtime))
            msbuild_project_pm = os.path.join(self._source_subfolder, "src", "tools", "msvc", "MSBuildProject.pm")
            tools.replace_in_file(msbuild_project_pm, "</Link>", """</Link>
    <Lib>
      <TargetMachine>$targetmachine</TargetMachine>
    </Lib>""")
            tools.replace_in_file(msbuild_project_pm, "'MultiThreadedDebugDLL'", "'%s'" % runtime)
            tools.replace_in_file(msbuild_project_pm, "'MultiThreadedDLL'", "'%s'" % runtime)
            config_default_pl = os.path.join(self._source_subfolder, "src", "tools", "msvc", "config_default.pl")
            solution_pm = os.path.join(self._source_subfolder, "src", "tools", "msvc", "Solution.pm")
            if self.options.with_openssl:
                for ssl in ["VC\libssl32", "VC\libssl64", "libssl"]:
                    tools.replace_in_file(solution_pm,
                                          "%s.lib" % ssl,
                                          "%s.lib" % self.deps_cpp_info["openssl"].libs[0])
                for crypto in ["VC\libcrypto32", "VC\libcrypto64", "libcrypto"]:
                    tools.replace_in_file(solution_pm,
                                          "%s.lib" % crypto,
                                          "%s.lib" % self.deps_cpp_info["openssl"].libs[1])
                tools.replace_in_file(config_default_pl,
                                      "openssl   => undef",
                                      "openssl   => '%s'" % self.deps_cpp_info["openssl"].rootpath.replace("\\", "/"))
            with tools.vcvars(self.settings):
                config = "DEBUG" if self.settings.build_type == "Debug" else "RELEASE"
                with tools.environment_append({"CONFIG": config}):
                    with tools.chdir(os.path.join(self._source_subfolder, "src", "tools", "msvc")):
                        self.run("perl build.pl libpq")
                        if not self.options.shared:
                            self.run("perl build.pl libpgport")
        else:
            autotools = self._configure_autotools()
            with tools.chdir(os.path.join(self._source_subfolder, "src", "backend")):
                autotools.make(args=self._make_args, target="generated-headers")
            with tools.chdir(os.path.join(self._source_subfolder, "src", "common")):
                autotools.make(args=self._make_args)
            with tools.chdir(os.path.join(self._source_subfolder, "src", "include")):
                autotools.make(args=self._make_args)
            with tools.chdir(os.path.join(self._source_subfolder, "src", "interfaces", "libpq")):
                autotools.make(args=self._make_args)
            with tools.chdir(os.path.join(self._source_subfolder, "src", "bin", "pg_config")):
                autotools.make(args=self._make_args)

    def package(self):
            self.copy("*.h", dst="include", src="src/interfaces/libpq/")
            self.copy("*.h", dst="include", src="src/include/")
            # By default, files are copied recursively. To avoid that we are specifying keep_path=False
            self.copy("*.so*", dst="lib", src="src/interfaces/libpq/", keep_path=False)


