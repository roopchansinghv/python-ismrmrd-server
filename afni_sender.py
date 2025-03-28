
import ismrmrd
import os
import itertools
import logging
import traceback
import numpy as np
import xml.dom.minidom
import base64
import ctypes
import mrdhelper
import constants

from connection import Connection

import socket
import time

# Folder for debug output files
debugFolder = "/tmp/share/debug"



# Sample client TCP code:
#
# import socket
#
# HOST = '127.0.0.1'  # Server IP address
# PORT = 65432        # Server port
# with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#    s.connect((HOST, PORT))
#    message = "Hello, server!"
#    s.sendall(message.encode('utf-8'))
#    data = s.recv(1024)
#
# print('Received:', data.decode('utf-8'))


# Sample server TCP code:
#
# import socket
#
# # Create a socket object
# server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# # Get local machine name and port
# host = socket.gethostname()
# port = 65432

# # Bind to the port
# server_socket.bind((host, port))

# # Queue up to 5 requests
# server_socket.listen(5)

# print(f"Server listening on {host}:{port}")

# while True:
#     # Establish a connection
#     client_socket, addr = server_socket.accept()
#     print(f"Got connection from {addr}")
#
#     msg = 'Thank you for connecting!'
#     client_socket.send(msg.encode('ascii'))
#     client_socket.close()



# see afni_src_dir/src/rickr/realtime.h for C-implementation of ART_comm C-struct
#
# and:
#
#    https://dev.to/totally_chase/porting-c-structs-into-python-because-speed-2aio
#
# for examples of 'porting' C-structs into Python, if needed.

# typedef struct
# {
    # int       state;                    /* state of AFNI realtime             */
    # int       mode;                     /* if > 0, then means AFNI is active */
    # int       use_tcp;                  /* if > 0, use TCP/IP to send data  */
    # int       swap;                     /* byte swap data before sending   */
    # int       byte_order;               /* note the byte order of images  */
    # int       is_oblique;               /* is the data oblique?          */
    # char    * zorder;                   /* slice order over time        */
    # char      host[ART_NAME_LEN];       /* hostname of CPU afni is on  */
    # char      ioc_name[ART_NAME_LEN];   /* I/O channel name to afni   */
    # char      buf[1280];                /* main buffer for afni comm */
    # float     oblique_xform[16];        /* oblique transformation   */
    # IOCHAN  * ioc;                      /* ptr to I/O channel struct */
    # param_t * param;                    /* local pointer to images  */
# } ART_comm;

# from ctypes import *
#
# class ART_comm_py(Structure):
#    _fields_ = [('state',       c_int),
#                ('mode',        c_int),
#                ('use_tcp',     c_int),
#                ('swap',        c_int),
#                ('byte_order',  c_int),
#                ('is_oblique',  c_int),
#                ('is_oblique',  c_int),
#                ('is_oblique',  c_int),
#                ('is_oblique',  c_int),
#                ('is_oblique',  c_int),
#                ('is_oblique',  c_int),
#                ('is_oblique',  c_int),
#                ('is_oblique',  c_int),
#               ]



def process(connection, config, metadata, afni_host, afni_port_control, afni_port_data):

    logging.info("Config: \n%s", config)

    # Open control connection to AFNI
    afni_socket_control = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    afni_socket_control.connect ((afni_host, afni_port_control))
    data_port_string = 'tcp:' + str(afni_host) + ':' + str(afni_port_data) + '\0'
    afni_socket_control.sendall(bytes(data_port_string, 'utf-8'))
    afni_socket_control.close()
    time.sleep(3)

    afni_socket_data = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    afni_socket_data.connect ((afni_host, afni_port_control))
    time.sleep(3)
    afni_socket_data.close()

    # now, once we have data, can use:
    #
    # afni_socket_data.sendall (data)
    #
    # to send image data into AFNI

    # Metadata should be MRD formatted header, but may be a string
    # if it failed conversion earlier
    try:
        # Disabled due to incompatibility between PyXB and Python 3.8:
        # https://github.com/pabigot/pyxb/issues/123
        # # logging.info("Metadata: \n%s", metadata.toxml('utf-8'))

        logging.info("Incoming dataset contains %d encodings", len(metadata.encoding))
        logging.info("First encoding is of type '%s', with a matrix size of (%s x %s x %s) and a field of view of (%s x %s x %s)mm^3",
            metadata.encoding[0].trajectory,
            metadata.encoding[0].encodedSpace.matrixSize.x,
            metadata.encoding[0].encodedSpace.matrixSize.y,
            metadata.encoding[0].encodedSpace.matrixSize.z,
            metadata.encoding[0].encodedSpace.fieldOfView_mm.x,
            metadata.encoding[0].encodedSpace.fieldOfView_mm.y,
            metadata.encoding[0].encodedSpace.fieldOfView_mm.z)

    except:
        logging.info("Improperly formatted metadata: \n%s", metadata)

    # Continuously parse incoming data parsed from MRD messages
    currentSeries = 0
    imgGroup = []
    waveformGroup = []
    try:
        for item in connection:
            # ----------------------------------------------------------
            # Raw k-space data messages
            # ----------------------------------------------------------
            if isinstance(item, ismrmrd.Acquisition):
                logging.info("Received raw (k-space data) - AFNI cannot currently process these.")
                break

            # ----------------------------------------------------------
            # Image data messages
            # ----------------------------------------------------------
            elif isinstance(item, ismrmrd.Image):
                # When this criteria is met, run process_group() on the accumulated
                # data, which returns images that are sent back to the client.
                # e.g. when the series number changes:
                if item.image_series_index != currentSeries:
                    logging.info("Processing a group of images because series index changed to %d", item.image_series_index)
                    currentSeries = item.image_series_index
                    image = process_image(imgGroup, connection, config, metadata)
                    connection.send_image(image)
                    imgGroup = []

                # Only process magnitude images -- send phase images back without modification (fallback for images with unknown type)
                if (item.image_type is ismrmrd.IMTYPE_MAGNITUDE) or (item.image_type == 0):
                    imgGroup.append(item)
                else:
                    tmpMeta = ismrmrd.Meta.deserialize(item.attribute_string)
                    tmpMeta['Keep_image_geometry']    = 1
                    item.attribute_string = tmpMeta.serialize()

                    connection.send_image(item)
                    continue

            # ----------------------------------------------------------
            # Waveform data messages
            # ----------------------------------------------------------
            elif isinstance(item, ismrmrd.Waveform):
                waveformGroup.append(item)

            elif item is None:
                break

            else:
                logging.error("Unsupported data type %s", type(item).__name__)

        # Extract raw ECG waveform data. Basic sorting to make sure that data
        # is time-ordered, but no additional checking for missing data.
        # ecgData has shape (5 x timepoints)
        if len(waveformGroup) > 0:
            waveformGroup.sort(key = lambda item: item.time_stamp)
            ecgData = [item.data for item in waveformGroup if item.waveform_id == 0]
            if len(ecgData) > 0:
                ecgData = np.concatenate(ecgData,1)

    except Exception as e:
        logging.error(traceback.format_exc())
        connection.send_logging(constants.MRD_LOGGING_ERROR, traceback.format_exc())

    finally:
        connection.send_close()



def process_image(images, connection, config, metadata):
    if len(images) == 0:
        return []

    # Create folder, if necessary
    if not os.path.exists(debugFolder):
        os.makedirs(debugFolder)
        logging.debug("Created folder " + debugFolder + " for debug output files")

    logging.debug("Processing data with %d images of type %s", len(images), ismrmrd.get_dtype_from_data_type(images[0].data_type))

    # Note: The MRD Image class stores data as [cha z y x]

    # Extract image data into a 5D array of size [img cha z y x]
    data = np.stack([img.data                              for img in images])
    head = [img.getHead()                                  for img in images]
    meta = [ismrmrd.Meta.deserialize(img.attribute_string) for img in images]

    # Reformat data to [y x z cha img], i.e. [row col] for the first two dimensions
    data = data.transpose((3, 4, 2, 1, 0))

    # Display MetaAttributes for first image
    logging.debug("MetaAttributes[0]: %s", ismrmrd.Meta.serialize(meta[0]))

    # Optional serialization of ICE MiniHeader
    if 'IceMiniHead' in meta[0]:
        logging.debug("IceMiniHead[0]: %s", base64.b64decode(meta[0]['IceMiniHead']).decode('utf-8'))

    logging.debug("Original image data is size %s" % (data.shape,))
    np.save(debugFolder + "/" + "imgOrig.npy", data)

    if ('parameters' in config) and ('options' in config['parameters']) and (config['parameters']['options'] == 'complex'):
        # Complex images are requested
        data = data.astype(np.complex64)
        maxVal = data.max()
    else:
        # Determine max value (12 or 16 bit)
        BitsStored = 12
        if (mrdhelper.get_userParameterLong_value(metadata, "BitsStored") is not None):
            BitsStored = mrdhelper.get_userParameterLong_value(metadata, "BitsStored")
        maxVal = 2**BitsStored - 1

        # Normalize and convert to int16
        data = data.astype(np.float64)
        data *= maxVal/data.max()
        data = np.around(data)
        data = data.astype(np.int16)

    # Invert image contrast
    data = maxVal-data
    data = np.abs(data)
    np.save(debugFolder + "/" + "imgInverted.npy", data)

    currentSeries = 0

    # Re-slice back into 2D images
    imagesOut = [None] * data.shape[-1]
    for iImg in range(data.shape[-1]):
        # Create new MRD instance for the inverted image
        # Transpose from convenience shape of [y x z cha] to MRD Image shape of [cha z y x]
        # from_array() should be called with 'transpose=False' to avoid warnings, and when called
        # with this option, can take input as: [cha z y x], [z y x], or [y x]
        imagesOut[iImg] = ismrmrd.Image.from_array(data[...,iImg].transpose((3, 2, 0, 1)), transpose=False)

        # Create a copy of the original fixed header and update the data_type
        # (we changed it to int16 from all other types)
        oldHeader = head[iImg]
        oldHeader.data_type = imagesOut[iImg].data_type

        # Set the image_type to match the data_type for complex data
        if (imagesOut[iImg].data_type == ismrmrd.DATATYPE_CXFLOAT) or (imagesOut[iImg].data_type == ismrmrd.DATATYPE_CXDOUBLE):
            oldHeader.image_type = ismrmrd.IMTYPE_COMPLEX

        # Unused example, as images are grouped by series before being passed into this function now
        # oldHeader.image_series_index = currentSeries

        # Increment series number when flag detected (i.e. follow ICE logic for splitting series)
        if mrdhelper.get_meta_value(meta[iImg], 'IceMiniHead') is not None:
            if mrdhelper.extract_minihead_bool_param(base64.b64decode(meta[iImg]['IceMiniHead']).decode('utf-8'), 'BIsSeriesEnd') is True:
                currentSeries += 1

        imagesOut[iImg].setHead(oldHeader)

        # Create a copy of the original ISMRMRD Meta attributes and update
        tmpMeta = meta[iImg]
        tmpMeta['DataRole']                       = 'Image'
        tmpMeta['ImageProcessingHistory']         = ['PYTHON', 'INVERT']
        tmpMeta['WindowCenter']                   = str((maxVal+1)/2)
        tmpMeta['WindowWidth']                    = str((maxVal+1))
        tmpMeta['SequenceDescriptionAdditional']  = 'FIRE'
        tmpMeta['Keep_image_geometry']            = 1

        if ('parameters' in config) and ('options' in config['parameters']):
            # Example for setting colormap
            if config['parameters']['options'] == 'colormap':
                tmpMeta['LUTFileName'] = 'MicroDeltaHotMetal.pal'

        # Add image orientation directions to MetaAttributes if not already present
        if tmpMeta.get('ImageRowDir') is None:
            tmpMeta['ImageRowDir'] = ["{:.18f}".format(oldHeader.read_dir[0]), "{:.18f}".format(oldHeader.read_dir[1]), "{:.18f}".format(oldHeader.read_dir[2])]

        if tmpMeta.get('ImageColumnDir') is None:
            tmpMeta['ImageColumnDir'] = ["{:.18f}".format(oldHeader.phase_dir[0]), "{:.18f}".format(oldHeader.phase_dir[1]), "{:.18f}".format(oldHeader.phase_dir[2])]

        metaXml = tmpMeta.serialize()
        logging.debug("Image MetaAttributes: %s", xml.dom.minidom.parseString(metaXml).toprettyxml())
        logging.debug("Image data has %d elements", imagesOut[iImg].data.size)

        imagesOut[iImg].attribute_string = metaXml

    return imagesOut



if __name__ == "__main__":

   # insert code here to initialize and call above 'process' routine
   #
   # i.e.

   time.sleep(9)
   process(None, None, None, 'localhost', 7961, 7960)

