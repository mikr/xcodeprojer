#!/usr/bin/env ruby
# encoding: utf-8
#
# Copyright (c) 2014 Michael Krause ( http://krause-software.com/ ).
#
# You are free to use this code under the MIT license:
# http://opensource.org/licenses/MIT
#
# Here is a simple example how to read an Xcode project into a Ruby hash,
# manipulate it and write it back in the canonical Xcode plist format.
# In this example a new buildphase is added to a test project every time
# this script is run.
#

require 'json'
require 'open3'
require 'tmpdir'
require 'Shellwords'

INTL_PROJECT_FILENAME = '../tests/data/IŋƫƐrnætiønæl X©ødǝ ¶®øjæƈt.xcodeproj/project.pbxproj'
XCODEPROJER = File.join(File.dirname(File.dirname(File.absolute_path(__FILE__))), 'xcodeprojer.py')


def rel(path)
  File.absolute_path(File.join(File.dirname(File.absolute_path(__FILE__)), path))
end

def find_isas(root, isa)
  root['objects'].each do |key, obj|
    if obj['isa'] == isa
      yield key, obj
    end
  end
end

def find_first(root, isa)
  find_isas(root, isa) do |key, obj|
    return obj if obj['isa'] == isa
  end
end

def fetch_gids(n)
  cmd = %Q|#{XCODEPROJER.shellescape} --gid #{n.to_s.shellescape}|
  stdout_str, stderr_str, status = Open3.capture3(cmd)
  stdout_str
end

def convert(projectdata, format, projectname)
  cmd = %Q|#{XCODEPROJER.shellescape} --convert #{format.shellescape} --projectname #{projectname.shellescape} -o -|
  stdout_str, stderr_str, status = Open3.capture3(cmd, :stdin_data=>projectdata)
  if status.exitstatus == 0
    stdout_str
  else
    STDERR.puts stderr_str
    nil
  end
end

def rundiff(old, new)
  cmd = %Q|/usr/bin/diff -u #{old.shellescape} #{new.shellescape}|
  puts cmd
  stdout_str, stderr_str, status = Open3.capture3(cmd)
  puts stdout_str
end

def getobj(root, gid)
  root['objects'][gid]
end


pbxfilename = rel(INTL_PROJECT_FILENAME)
qpbxfilename = pbxfilename.shellescape

xcodeproj = File.basename(File.dirname(pbxfilename))
ext = File.extname(xcodeproj)

if ['.xcodeproj', '.xcode', '.pbproj', '.pbxproj'].include? ext
  projname = File.basename(xcodeproj, ext)
else
  STDERR.puts %Q|Cannot determine the project name from the parent directory of #{qpbxfilename}|
  exit(1)
end

inputfile = File.open(pbxfilename, 'rb')
contents = inputfile.read
inputfile.close
jsondata = convert(contents, 'json', projname)

if jsondata.nil?
  STDERR.puts "Converting #{pbxfilename} to JSON failed."
  exit(1)
end

root = JSON.load(jsondata)

pbxproject = find_first(root, 'PBXProject')

if pbxproject
  # Fetch as many gids as you like
  freshgids = fetch_gids(5).lines
  firsttarget = getobj(root, pbxproject['targets'][0])

  # Construct a new buildphase as any other JSON object
  newbuildphase = {"isa" => "PBXShellScriptBuildPhase",
                   "buildActionMask" => "2147483647",
                   "files" => [],
                   "inputPaths" => [],
                   "outputPaths" => [],
                   "runOnlyForDeploymentPostprocessing" => "0",
                   "shellPath" => "/bin/sh",
                   "shellScript" => 'echo "A new buildphase says hi!"'}
  id_newbuildphase = freshgids[0]
  root['objects'][id_newbuildphase] = newbuildphase
  firsttarget['buildPhases'].insert(0, id_newbuildphase)
  newjsondata = JSON.generate(root)
  xcodeprojectdata = convert(newjsondata, 'xcode', projname)

  puts %Q|Adding a new buildphase with a dynamically generated Xcode id to #{qpbxfilename}|
  puts

  tmpname = File.join(Dir.tmpdir, Dir::Tmpname.make_tmpname(['projer', '.pbxproj'], nil))
  projbackup = File.open(tmpname, 'wb')
  begin
    projbackup.write(contents)
    puts %Q|Saved the old contents of #{qpbxfilename} to #{tmpname.shellescape}|
  ensure
    projbackup.close
  end

  outputfile = File.open(pbxfilename, 'wb')
  outputfile.write(xcodeprojectdata)
  outputfile.close

  rundiff(tmpname, pbxfilename)
else
  STDERR.puts "Did not find a PBXProject."
  exit(1)
end
