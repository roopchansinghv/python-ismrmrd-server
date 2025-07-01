
#!/usr/bin/env python
# coding: utf-8

import   os
import   sys
import   numpy          as       np
import   ismrmrd        as       mrd
import   ismrmrd.xsd
from     matplotlib     import   pyplot   as plt
import   h5py
import   nibabel        as       nib



### Following [this](https://gadgetron.discourse.group/t/reading-ismrmrd-image-type/322/4) suggestion from David Hansen

## First - read in file with reconstructed image data
f = mrd.File('reconstructed_data.h5')

# We need to find all image groups / sets within the ISMRMRD image HDF5 file
image_sets = [f[image_set].images for image_set in f.find_images()]

len(image_sets)

# This should now tell us how many images are present within a give image group/set.
# Should look up a better way to do this iteration.
image_sets[0].headers.size

header_keys_for_nifti = [
  "data_type",
  "flags",
  "matrix_size",
  "field_of_view",
  "channels",
  "position",
  "read_dir",
  "phase_dir",
  "slice_dir",
  "slice",
  "contrast",
  "repetition",
  "acquisition_time_stamp",
  "physiology_time_stamp",
  "image_type",
  "image_index",
  "image_series_index"
]

# Iterate over all sets within the ISMRMRD file. This should generate 1 NIFTI file per group (to be later confirmed)
for image_set_index, image_set in enumerate(image_sets):
   print ("Max slice index value in this image set is: %d" % max(image_set.headers[:]["slice"]))
   # Now iterate over all images within each set.  Hopefully each image within a set has the same dimensions
   # for j in range(image_set.headers.size):
      # for header_value_key in header_keys_for_nifti:
         # print ("Header value %27s from image set %d is: %s" % (header_value_key, j, image_set.headers[j][header_value_key]))

   # According to https://ismrmrd.readthedocs.io/en/latest/mrd_image_data.html#imageheader, the dimensions of the
   # ISMRMRD image data set should be matrix_size[0], matrix_size[1], matrix_size[2], channels, then the 'images'
   # themselves ... or rather the exact reverse of this ...
   print("Shape of ISMRMRD data is: " + str(image_set.data.shape))

   # Create NIFTI-1 dataset from one of the data arrays read in from the ISMRMRD image sets.
   # Transpose seems to be necessary to pack data properly
   nii_image_data = image_set.data[0::].transpose(4,3,2,1,0)

   print("Shape of NIFTI data is: " + str(nii_image_data.shape))

   # Then, create NIFTI data set in memory from image data component from ISMRMRD image sets.  The NIFTI data set
   # should inherit those data's dimensions and data types, which should leave the geometry and position information
   # to be later computed and filled in.
   new_nii = nib.Nifti1Image(nii_image_data, None)

   # According to https://github.com/NIFTI-Imaging/nifti_clib/blob/master/nifti2/nifti1.h, lines 1310 - 1350 (approx),
   # get units of space and time for values packed into header. Distance units in mm == 2, and time units in ms == 16
   # (defaults for ISMRMRD image header).  See if there's way to get these symbolically, instead of hard-coding ...
   new_nii.header.set_xyzt_units(xyz=2, t=16)

   # print("\nNew nii header: " + str(new_nii.header))

   # Can access NIFTI header elements through keys, similar to how the ISMRMRD image header values above are accessed.
   # print("Original header dim:" + str(new_nii.header['dim']))

   # Can change these, from ISMRMRD header values, as needed.
   new_nii.header['dim'] = [  5, 144, 144,   1,   1,  7,   1,   1]

   # print("New header dim:" + str(new_nii.header['dim']))

   print("\nUpdated nii header: " + str(new_nii.header))

   nib.save(new_nii, 'new_test_nifti_%09d.nii' % image_set_index)

