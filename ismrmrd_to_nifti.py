
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



## First - read in file with reconstructed image data
f = ismrmrd.File('reconstructed_data.h5')

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
for image_set in image_sets:
   # Now iterate over all images within each set.  Hopefully each image within a set has the same dimensions
   for j in range(image_set.headers.size):
      for header_value_key in header_keys_for_nifti:
         print ("Header value %27s from image set %d is: %s" % (header_value_key, j, image_set.headers[j][header_value_key]))


### Now create NIFTI-1 dataset from one of the data arrays read in from the ISMRMRD image sets.

# Transpose seems to be necessary to pack data properly
nii_image_data = image_sets[0].data[0::].transpose(4,3,2,1,0)


# Then, create NIFTI data set in memory from image data component from ISMRMRD image sets.  The NIFTI data set
# should inherit those data's dimensions and data types, which should leave the geometry and position information
# to be later computed and filled in.
new_nii = nib.Nifti1Image(nii_image_data, None)

print("\nNew nii header: " + str(new_nii.header))

# Can access NIFTI header elements through keys, similar to how the ISMRMRD image header values above are accessed.
new_nii.header['dim']

# Can change these, from ISMRMRD header values, as needed.
# new_nii.header['dim'] = [  5, 256, 256,   3,   1,   1,   1,   1]

new_nii.header['dim']

nib.save(new_nii, 'new_test_nifti.nii')

